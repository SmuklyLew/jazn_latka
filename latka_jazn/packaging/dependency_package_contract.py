from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any, Mapping
import uuid
import zipfile

from latka_jazn.dependencies.common import DEPENDENCY_ARTIFACT_SCHEMA, LOCK_NAME, MANIFEST_NAME
from latka_jazn.dependencies.wheelhouse import read_manifest, sha256_file, verify_bundle
from latka_jazn.packaging.zip_resource_limits import validate_zip_resources
from latka_jazn.tools.safe_paths import validate_safe_relative_path

DEPENDENCY_ARTIFACT_NAME = "JAZN_DEPENDENCY_ARTIFACT.json"
_TARGET_IDENTITY_FIELDS = (
    "alias",
    "python_version",
    "implementation",
    "abi",
    "platform_family",
    "architecture",
    "libc_family",
)


class DependencyPackageError(ValueError):
    pass


def _deterministic_zipinfo(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o100644 << 16
    info.create_system = 3
    return info


def dependency_artifact_descriptor(bundle_dir: Path | str) -> dict[str, Any]:
    bundle = Path(bundle_dir).resolve()
    verification = verify_bundle(bundle)
    if verification.get("ok") is not True:
        raise DependencyPackageError(f"dependency bundle is not verified: {verification.get('errors')}")
    manifest = read_manifest(bundle / MANIFEST_NAME) or {}
    return {
        "schema_version": DEPENDENCY_ARTIFACT_SCHEMA,
        "created_at_utc": manifest.get("created_at_utc"),
        "runtime_version": manifest.get("runtime_version"),
        "bundle_name": manifest.get("bundle_name") or bundle.name,
        "profiles": list(manifest.get("profiles") or []),
        "resolved_profiles": list(manifest.get("resolved_profiles") or []),
        "target": dict(manifest.get("target") or {}),
        "dependency_contract_fingerprint": manifest.get("dependency_contract_fingerprint"),
        "wheelhouse_manifest_sha256": sha256_file(bundle / MANIFEST_NAME),
        "hash_lock_sha256": sha256_file(bundle / LOCK_NAME),
        "wheel_count": verification.get("wheel_count"),
        "truth_boundary": "Artifact is transport for one verified Wheelhouse Contract v2 bundle; environments/site-packages are never transported.",
    }


def build_dependency_sidecar(bundle_dir: Path | str, output_zip: Path | str) -> dict[str, Any]:
    bundle = Path(bundle_dir).resolve()
    output = Path(output_zip).resolve()
    descriptor = dependency_artifact_descriptor(bundle)
    members = [bundle / MANIFEST_NAME, bundle / LOCK_NAME, *sorted(bundle.glob("*.whl"), key=lambda p: p.name.lower())]
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = output.with_name(output.name + f".tmp-{uuid.uuid4().hex}")
    descriptor_bytes = json.dumps(descriptor, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
    try:
        with zipfile.ZipFile(temp, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as archive:
            archive.writestr(_deterministic_zipinfo(DEPENDENCY_ARTIFACT_NAME), descriptor_bytes)
            for path in members:
                archive.writestr(_deterministic_zipinfo(path.name), path.read_bytes())
        os.replace(temp, output)
    finally:
        temp.unlink(missing_ok=True)
    verification = verify_dependency_sidecar(output)
    if verification.get("ok") is not True:
        output.unlink(missing_ok=True)
        raise DependencyPackageError(f"built dependency sidecar failed verification: {verification.get('errors')}")
    return {
        "filename": output.name,
        "size_bytes": output.stat().st_size,
        "sha256": sha256_file(output),
        "role": "dependencies",
        "descriptor": descriptor,
        "verification": verification,
    }


def _read_descriptor(archive: zipfile.ZipFile) -> dict[str, Any]:
    try:
        payload = json.loads(archive.read(DEPENDENCY_ARTIFACT_NAME).decode("utf-8"))
    except (KeyError, UnicodeError, json.JSONDecodeError) as exc:
        raise DependencyPackageError(f"dependency descriptor unreadable: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != DEPENDENCY_ARTIFACT_SCHEMA:
        raise DependencyPackageError("unsupported dependency artifact schema")
    return payload


def verify_dependency_sidecar(zip_path: Path | str, *, expected_sha256: str | None = None,
                              expected_target: Mapping[str, Any] | None = None) -> dict[str, Any]:
    source = Path(zip_path).resolve()
    errors: list[dict[str, Any]] = []
    if not source.is_file() or source.is_symlink():
        return {"ok": False, "path": str(source), "errors": [{"code": "sidecar_missing_or_not_regular"}]}
    if expected_sha256 and sha256_file(source) != expected_sha256.lower():
        return {"ok": False, "path": str(source), "errors": [{"code": "sidecar_sha256_mismatch"}]}
    descriptor: dict[str, Any] = {}
    staging = Path(tempfile.mkdtemp(prefix="jazn-dependency-sidecar-"))
    try:
        with zipfile.ZipFile(source) as archive:
            validate_zip_resources(archive)
            names: set[str] = set()
            for info in archive.infolist():
                if info.is_dir():
                    continue
                name = validate_safe_relative_path(info.filename)
                if "/" in name or name in names:
                    errors.append({"code": "sidecar_member_layout_invalid", "member": name})
                    continue
                names.add(name)
            if DEPENDENCY_ARTIFACT_NAME not in names or MANIFEST_NAME not in names or LOCK_NAME not in names:
                errors.append({"code": "sidecar_required_member_missing"})
            if errors:
                return {"ok": False, "path": str(source), "errors": errors}
            descriptor = _read_descriptor(archive)
            for info in archive.infolist():
                if info.is_dir():
                    continue
                target = staging / info.filename
                target.write_bytes(archive.read(info.filename))
        actual_target = descriptor.get("target") if isinstance(descriptor.get("target"), dict) else {}
        bundle_verify = verify_bundle(staging)
        if bundle_verify.get("ok") is not True:
            errors.append({"code": "wheelhouse_verification_failed", "detail": bundle_verify.get("errors")})
        bundle_target = bundle_verify.get("target") if isinstance(bundle_verify.get("target"), dict) else {}
        for key in _TARGET_IDENTITY_FIELDS:
            if str(actual_target.get(key) or "") != str(bundle_target.get(key) or ""):
                errors.append({"code": "descriptor_target_manifest_mismatch", "field": key})

        if expected_target:
            for key in _TARGET_IDENTITY_FIELDS:
                wanted = expected_target.get(key)
                if wanted not in (None, "") and str(actual_target.get(key) or "") != str(wanted):
                    errors.append({"code": "sidecar_target_mismatch", "field": key})
            host_tags = set(str(tag) for tag in expected_target.get("compatible_platform_tags") or [])
            if host_tags:
                manifest = read_manifest(staging / MANIFEST_NAME) or {}
                for item in manifest.get("resolved_distributions") or []:
                    if not isinstance(item, Mapping):
                        continue
                    wheel_tags = set(str(tag) for tag in item.get("tags") or [])
                    if wheel_tags and not wheel_tags.intersection(host_tags):
                        errors.append({
                            "code": "sidecar_wheel_host_incompatible",
                            "distribution": item.get("name"),
                            "filename": item.get("filename"),
                        })
        if descriptor.get("wheelhouse_manifest_sha256") != sha256_file(staging / MANIFEST_NAME):
            errors.append({"code": "descriptor_manifest_sha256_mismatch"})
        if descriptor.get("hash_lock_sha256") != sha256_file(staging / LOCK_NAME):
            errors.append({"code": "descriptor_lock_sha256_mismatch"})
        return {"ok": not errors, "path": str(source), "sha256": sha256_file(source),
                "descriptor": descriptor, "bundle_verification": bundle_verify, "errors": errors}
    except (OSError, zipfile.BadZipFile, ValueError, DependencyPackageError) as exc:
        return {"ok": False, "path": str(source), "errors": [{"code": "sidecar_unreadable", "detail": f"{type(exc).__name__}:{exc}"}]}
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def extract_verified_dependency_sidecar(zip_path: Path | str, destination: Path | str,
                                        *, expected_sha256: str | None = None,
                                        expected_target: Mapping[str, Any] | None = None) -> dict[str, Any]:
    source = Path(zip_path).resolve()
    target = Path(destination).resolve()
    verification = verify_dependency_sidecar(source, expected_sha256=expected_sha256, expected_target=expected_target)
    if verification.get("ok") is not True:
        raise DependencyPackageError(f"dependency sidecar verification failed: {verification.get('errors')}")
    staging = target.with_name(target.name + f".extract-{uuid.uuid4().hex}")
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    try:
        with zipfile.ZipFile(source) as archive:
            for info in archive.infolist():
                if info.is_dir() or info.filename == DEPENDENCY_ARTIFACT_NAME:
                    continue
                (staging / info.filename).write_bytes(archive.read(info.filename))
        if target.exists():
            existing = verify_bundle(target)
            if existing.get("ok") is True and sha256_file(target / MANIFEST_NAME) == str((verification.get("descriptor") or {}).get("wheelhouse_manifest_sha256") or ""):
                shutil.rmtree(staging)
                return {"ok": True, "state": "dependency_bundle_reused", "bundle_dir": str(target), "verification": verification}
            raise DependencyPackageError(f"immutable dependency destination already exists with different contents: {target}")
        os.replace(staging, target)
        final = verify_bundle(target)
        if final.get("ok") is not True:
            raise DependencyPackageError(f"extracted dependency bundle failed verification: {final.get('errors')}")
        return {"ok": True, "state": "dependency_bundle_extracted", "bundle_dir": str(target), "verification": verification}
    finally:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
