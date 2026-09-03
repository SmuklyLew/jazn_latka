from __future__ import annotations

import base64
import csv
from datetime import datetime, timezone
from email.parser import Parser
import hashlib
import importlib.metadata
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Any, Mapping, Sequence
import uuid
import zipfile

from .common import (
    DEFAULT_TIMEOUT_SECONDS,
    LOCK_NAME,
    MANIFEST_NAME,
    WHEELHOUSE_SCHEMA,
    DependencyStudioError,
    TargetSpec,
    canonicalize_distribution_name,
    default_wheelhouse_root,
    dependency_contract_fingerprint,
    expand_profile_names,
    normalize_python_version,
    resolve_profile_requirements,
    runtime_version,
    target_spec,
)


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_json(payload: Any) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def release_lock_path(root: Path | str, profile_names: Sequence[str], target: TargetSpec) -> Path:
    slug = "+".join(
        re.sub(r"[^a-z0-9._+-]+", "-", str(profile).lower()).strip("-")
        for profile in profile_names
        if str(profile).strip()
    ) or "default"
    py_digits = target.python_version.replace(".", "")
    return (
        Path(root).resolve()
        / "latka_jazn"
        / "resources"
        / "dependencies"
        / "locks"
        / slug
        / f"{target.alias}-py{py_digits}.txt"
    )


def read_manifest(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def build_download_command(*, python_executable: str, destination: Path,
                           requirements: Sequence[str], target: TargetSpec) -> list[str]:
    cmd = [python_executable, "-m", "pip", "download", "--disable-pip-version-check",
           "--dest", str(destination), "--only-binary=:all:"]
    if target.pip_platform:
        cmd += ["--platform", target.pip_platform, "--python-version", target.python_version,
                "--implementation", target.implementation]
        if target.abi:
            cmd += ["--abi", target.abi]
    return [*cmd, *requirements]


def build_locked_download_command(*, python_executable: str, destination: Path,
                                  lock_file: Path, target: TargetSpec) -> list[str]:
    cmd = [python_executable, "-m", "pip", "download", "--disable-pip-version-check",
           "--dest", str(destination), "--only-binary=:all:", "--require-hashes", "-r", str(lock_file)]
    if target.pip_platform:
        cmd += ["--platform", target.pip_platform, "--python-version", target.python_version,
                "--implementation", target.implementation]
        if target.abi:
            cmd += ["--abi", target.abi]
    return cmd


def _decode_record_digest(value: str) -> tuple[str, bytes]:
    algorithm, sep, encoded = str(value or "").partition("=")
    if not sep or algorithm.lower() not in hashlib.algorithms_available:
        raise DependencyStudioError(f"Unsupported RECORD digest: {value!r}")
    try:
        digest = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
    except Exception as exc:
        raise DependencyStudioError(f"Invalid RECORD digest encoding: {value!r}") from exc
    return algorithm.lower(), digest


def _record_verification(zf: zipfile.ZipFile, record_name: str) -> dict[str, Any]:
    try:
        rows = list(csv.reader(io.StringIO(zf.read(record_name).decode("utf-8"))))
    except (KeyError, UnicodeError, csv.Error) as exc:
        raise DependencyStudioError(f"Wheel RECORD unreadable: {record_name}: {exc}") from exc
    seen: set[str] = set()
    verified = 0
    missing_hash: list[str] = []
    invalid: list[str] = []
    names = {info.filename for info in zf.infolist() if not info.is_dir()}
    optional_unrecorded_suffixes = (".dist-info/RECORD.jws", ".dist-info/RECORD.p7s")
    for row in rows:
        if len(row) != 3:
            invalid.append("<malformed-row>")
            continue
        name, digest_text, size_text = row
        if name in seen:
            invalid.append(name)
            continue
        seen.add(name)
        if name not in names:
            invalid.append(name)
            continue
        data = zf.read(name)
        if size_text:
            try:
                if int(size_text) != len(data):
                    invalid.append(name)
                    continue
            except ValueError:
                invalid.append(name)
                continue
        is_record = name == record_name
        is_signature = name.endswith(optional_unrecorded_suffixes)
        if digest_text:
            algorithm, expected = _decode_record_digest(digest_text)
            actual = hashlib.new(algorithm, data).digest()
            if actual != expected:
                invalid.append(name)
                continue
            if algorithm not in {"sha256", "sha384", "sha512"}:
                invalid.append(name)
                continue
            verified += 1
        elif not (is_record or is_signature):
            missing_hash.append(name)
    unlisted = sorted(name for name in names - seen if not name.endswith(optional_unrecorded_suffixes))
    if invalid or missing_hash or unlisted:
        raise DependencyStudioError(
            "Wheel RECORD verification failed: "
            f"invalid={invalid[:5]} missing_hash={missing_hash[:5]} unlisted={unlisted[:5]}"
        )
    return {
        "ok": True,
        "record_name": record_name,
        "entry_count": len(rows),
        "hashed_entry_count": verified,
        "unlisted_entry_count": 0,
        "missing_hash_count": 0,
    }


def _filename_metadata(path: Path) -> dict[str, Any]:
    try:
        from packaging.utils import parse_wheel_filename
    except ImportError as exc:
        raise DependencyStudioError("packaging is required for Wheelhouse Contract v2 validation") from exc
    try:
        name, version, build, tags = parse_wheel_filename(path.name)
    except Exception as exc:
        raise DependencyStudioError(f"Invalid wheel filename {path.name}: {exc}") from exc
    return {
        "distribution": str(name),
        "version": str(version),
        "build": list(build),
        "tags": sorted(str(tag) for tag in tags),
    }


def wheel_metadata(path: Path) -> dict[str, Any]:
    filename = _filename_metadata(path)
    try:
        with zipfile.ZipFile(path) as zf:
            bad = zf.testzip()
            if bad:
                raise DependencyStudioError(f"Wheel CRC failed: {path.name}:{bad}")
            names = zf.namelist()
            metas = [name for name in names if name.endswith(".dist-info/METADATA")]
            wheels = [name for name in names if name.endswith(".dist-info/WHEEL")]
            records = [name for name in names if name.endswith(".dist-info/RECORD")]
            if len(metas) != 1 or len(wheels) != 1 or len(records) != 1:
                raise DependencyStudioError(f"Wheel metadata layout invalid: {path.name}")
            message = Parser().parsestr(zf.read(metas[0]).decode("utf-8", errors="replace"))
            wheel_message = Parser().parsestr(zf.read(wheels[0]).decode("utf-8", errors="replace"))
            record = _record_verification(zf, records[0])
            license_files = sorted(name for name in names if ".dist-info/licenses/" in name and not name.endswith("/"))
    except (OSError, zipfile.BadZipFile, KeyError) as exc:
        raise DependencyStudioError(f"Invalid wheel {path}: {exc}") from exc
    classifiers = message.get_all("Classifier") or []
    metadata_name = canonicalize_distribution_name(str(message.get("Name") or ""))
    metadata_version = str(message.get("Version") or "")
    if metadata_name != canonicalize_distribution_name(filename["distribution"]):
        raise DependencyStudioError(f"Wheel Name mismatch: filename={filename['distribution']} metadata={message.get('Name')}")
    if metadata_version != filename["version"]:
        raise DependencyStudioError(f"Wheel Version mismatch: filename={filename['version']} metadata={metadata_version}")
    wheel_tags = sorted(str(item) for item in (wheel_message.get_all("Tag") or []))
    if wheel_tags and not set(wheel_tags).intersection(filename["tags"]):
        raise DependencyStudioError(f"Wheel WHEEL Tag does not match filename tags: {path.name}")
    return {
        "name": message.get("Name"),
        "version": metadata_version,
        "requires_python": message.get("Requires-Python"),
        "license_expression": message.get("License-Expression"),
        "license": message.get("License"),
        "license_files": license_files,
        "license_classifiers": [c for c in classifiers if str(c).startswith("License ::")],
        "filename": filename,
        "wheel_tags": wheel_tags,
        "record_verification": record,
    }


def _requires_python_ok(specifier: str | None, python_version: str) -> bool:
    if not specifier:
        return True
    try:
        from packaging.specifiers import SpecifierSet
        from packaging.version import Version
    except ImportError as exc:
        raise DependencyStudioError("packaging is required for Requires-Python validation") from exc
    try:
        return Version(python_version) in SpecifierSet(str(specifier))
    except Exception as exc:
        raise DependencyStudioError(f"Invalid Requires-Python {specifier!r}: {exc}") from exc


def _wheel_row(path: Path) -> dict[str, Any]:
    return {"filename": path.name, "size_bytes": path.stat().st_size,
            "sha256": sha256_file(path), "metadata": wheel_metadata(path)}


def _resolved_distributions(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    resolved: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        metadata = row.get("metadata") or {}
        filename = metadata.get("filename") or {}
        name = canonicalize_distribution_name(str(filename.get("distribution") or metadata.get("name") or ""))
        if not name or name in seen:
            raise DependencyStudioError(f"Duplicate or missing resolved distribution: {name!r}")
        seen.add(name)
        resolved.append({
            "name": name,
            "version": str(filename.get("version") or metadata.get("version") or ""),
            "filename": row["filename"],
            "sha256": row["sha256"],
            "size_bytes": row["size_bytes"],
            "requires_python": metadata.get("requires_python"),
            "license_expression": metadata.get("license_expression"),
            "license": metadata.get("license"),
            "license_files": list(metadata.get("license_files") or []),
            "tags": list(filename.get("tags") or []),
            "record_verified": bool((metadata.get("record_verification") or {}).get("ok")),
        })
    return sorted(resolved, key=lambda item: item["name"])


def render_hash_lock(resolved: Sequence[dict[str, Any]]) -> str:
    lines = ["# Generated by Jaźń Dependency Studio. Fully pinned, wheel-only, SHA-256 locked."]
    for item in sorted(resolved, key=lambda row: str(row["name"])):
        lines.append(f"{item['name']}=={item['version']} --hash=sha256:{item['sha256']}")
    return "\n".join(lines) + "\n"


def verify_hash_lock(directory: Path, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    lock_path = directory / LOCK_NAME
    if not lock_path.is_file() or lock_path.is_symlink():
        return [{"code": "hash_lock_missing"}]
    expected_sha = str(manifest.get("hash_lock_sha256") or "")
    if not expected_sha or sha256_file(lock_path) != expected_sha:
        errors.append({"code": "hash_lock_sha256_mismatch"})
    expected = render_hash_lock(manifest.get("resolved_distributions") or [])
    try:
        actual = lock_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        actual = ""
    if actual != expected:
        errors.append({"code": "hash_lock_content_mismatch"})
    return errors


def _verify_bundle_full(bundle_dir: Path | str) -> dict[str, Any]:
    directory = Path(bundle_dir).resolve()
    manifest_path = directory / MANIFEST_NAME
    manifest = read_manifest(manifest_path)
    if manifest is None:
        return {"ok": False, "bundle_dir": str(directory), "errors": [{"code": "manifest_unreadable"}]}
    errors: list[dict[str, Any]] = []
    if manifest.get("schema_version") != WHEELHOUSE_SCHEMA:
        errors.append({"code": "manifest_schema_unsupported"})
    target = _mapping(manifest.get("target"))
    target_tags = set(str(tag) for tag in target.get("compatible_platform_tags") or [])
    files = _list(manifest.get("files"))
    expected: set[str] = set()
    distributions: set[str] = set()
    verified = 0
    for row in files:
        if not isinstance(row, dict):
            errors.append({"code": "manifest_file_entry_invalid"})
            continue
        name = str(row.get("filename") or "")
        p = Path(name)
        if not name or p.name != name or p.suffix.lower() != ".whl" or name in expected:
            errors.append({"code": "wheel_filename_unsafe_or_duplicate", "filename": name})
            continue
        expected.add(name)
        wheel = directory / name
        if not wheel.is_file() or wheel.is_symlink():
            errors.append({"code": "wheel_missing_or_not_regular", "filename": name})
            continue
        if wheel.stat().st_size != int(row.get("size_bytes", -1)):
            errors.append({"code": "wheel_size_mismatch", "filename": name})
            continue
        if sha256_file(wheel) != str(row.get("sha256") or "").lower():
            errors.append({"code": "wheel_sha256_mismatch", "filename": name})
            continue
        try:
            actual = wheel_metadata(wheel)
        except DependencyStudioError as exc:
            errors.append({"code": "wheel_structure_invalid", "filename": name, "detail": str(exc)})
            continue
        declared = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
        if actual != declared:
            errors.append({"code": "wheel_metadata_mismatch", "filename": name})
            continue
        dist = canonicalize_distribution_name(str((actual.get("filename") or {}).get("distribution") or ""))
        if dist in distributions:
            errors.append({"code": "duplicate_distribution", "distribution": dist, "filename": name})
            continue
        distributions.add(dist)
        tags = set(str(tag) for tag in (actual.get("filename") or {}).get("tags") or [])
        if target_tags and not tags.intersection(target_tags):
            errors.append({"code": "wheel_target_incompatible", "filename": name})
            continue
        if not _requires_python_ok(actual.get("requires_python"), str(target.get("python_version") or "")):
            errors.append({"code": "requires_python_incompatible", "filename": name})
            continue
        if (actual.get("record_verification") or {}).get("ok") is not True:
            errors.append({"code": "record_not_verified", "filename": name})
            continue
        verified += 1
    actual_names = {p.name for p in directory.glob("*.whl") if p.is_file()}
    for extra in sorted(actual_names - expected):
        errors.append({"code": "unlisted_wheel", "filename": extra})
    resolved = _list(manifest.get("resolved_distributions"))
    if len(resolved) != len(distributions):
        errors.append({"code": "resolved_distribution_count_mismatch"})
    else:
        declared_names = {canonicalize_distribution_name(str(item.get("name") or "")) for item in resolved if isinstance(item, dict)}
        if declared_names != distributions:
            errors.append({"code": "resolved_distribution_inventory_mismatch"})
    errors.extend(verify_hash_lock(directory, manifest))
    return {
        "ok": not errors,
        "bundle_dir": str(directory),
        "manifest_path": str(manifest_path),
        "manifest_sha256": sha256_file(manifest_path) if manifest_path.is_file() else None,
        "hash_lock_path": str(directory / LOCK_NAME),
        "profiles": list(manifest.get("profiles") or []),
        "resolved_profiles": list(manifest.get("resolved_profiles") or manifest.get("profiles") or []),
        "requirements": list(manifest.get("requirements") or []),
        "target": target,
        "wheel_count": len(expected),
        "verified_wheel_count": verified,
        "record_verified_wheel_count": verified,
        "errors": errors,
        "truth_boundary": "v2 verifies SHA-256, CRC, METADATA/WHEEL/RECORD, filename Name/Version, target tags, Requires-Python, exact inventory and hash lock.",
    }


def verify_bundle(bundle_dir: Path | str) -> dict[str, Any]:
    directory = Path(bundle_dir).resolve()
    manifest_path = directory / MANIFEST_NAME
    manifest = read_manifest(manifest_path)
    if manifest is None:
        return _verify_bundle_full(directory)

    from .wheelhouse_bootstrap import packaging_runtime_available, unpacked_packaging_bootstrap

    if packaging_runtime_available():
        result = _verify_bundle_full(directory)
        result["validator_dependency_source"] = "ambient_unpacked_packaging"
        return result

    try:
        with unpacked_packaging_bootstrap(
            directory,
            manifest,
            sha256_file=sha256_file,
            record_verification=_record_verification,
        ) as bootstrap:
            result = _verify_bundle_full(directory)
            result["validator_dependency_source"] = str(bootstrap.get("mode") or "verified_unpacked_packaging_bootstrap")
            result["validator_bootstrap_wheel"] = bootstrap.get("wheel")
            return result
    except DependencyStudioError as exc:
        return {
            "ok": False,
            "bundle_dir": str(directory),
            "manifest_path": str(manifest_path),
            "manifest_sha256": sha256_file(manifest_path) if manifest_path.is_file() else None,
            "errors": [{"code": "validator_dependency_bootstrap_failed", "detail": str(exc)}],
            "validator_dependency_source": "unavailable",
            "truth_boundary": (
                "Wheelhouse v2 fails closed unless packaging validation is available from unpacked files; "
                "a hash/RECORD-verified packaging wheel may be unpacked to temporary staging, never imported from its archive."
            ),
        }


def _tool_version(executable: str, module: str) -> str | None:
    try:
        cp = subprocess.run([executable, "-c", f"import importlib.metadata; print(importlib.metadata.version('{module}'))"],
                            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30, check=False)
        return cp.stdout.strip() if cp.returncode == 0 and cp.stdout.strip() else None
    except (OSError, subprocess.SubprocessError):
        return None


def _manifest(
    root: Path,
    profiles: Sequence[str],
    requirements: Sequence[str],
    target: TargetSpec,
    wheels: Sequence[Path],
    command: Sequence[str],
    *,
    python_executable: str,
    input_lock_path: Path | None = None,
) -> dict[str, Any]:
    rows = [_wheel_row(path) for path in sorted(wheels, key=lambda path: path.name.lower())]
    resolved = _resolved_distributions(rows)
    request = {"profiles": sorted(profiles), "requirements": sorted(requirements), "target": target.to_dict()}
    resolution = [{"name": row["name"], "version": row["version"], "filename": row["filename"], "sha256": row["sha256"]} for row in resolved]
    return {
        "schema_version": WHEELHOUSE_SCHEMA,
        "runtime_version": runtime_version(),
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "project_root_name": root.name,
        "profiles": list(profiles),
        "resolved_profiles": list(expand_profile_names(root, profiles)),
        "requirements": list(requirements),
        "direct_requirements": list(requirements),
        "dependency_contract_fingerprint": dependency_contract_fingerprint(root, profiles),
        "target": target.to_dict(),
        "request_fingerprint": sha256_json(request),
        "resolution_fingerprint": sha256_json(resolution),
        "wheel_count": len(rows),
        "total_size_bytes": sum(int(row["size_bytes"]) for row in rows),
        "resolved_distributions": resolved,
        "files": rows,
        "download_command": list(command),
        "pip_version": _tool_version(python_executable, "pip"),
        "packaging_version": _tool_version(python_executable, "packaging"),
        "resolution_source": "release_hash_lock" if input_lock_path is not None else "direct_requirements",
        "input_hash_lock_sha256": sha256_file(input_lock_path) if input_lock_path is not None else None,
        "network_used_for_download": True,
        "install_policy": "offline_no_index_only_binary_require_hashes",
    }


def download_bundle(
    root: Path | str,
    *,
    profile_names: Sequence[str],
    python_version: str | None = None,
    platform_alias: str | None = None,
    python_executable: str | None = None,
    wheelhouse_root: Path | str | None = None,
    lock_file: Path | str | None = None,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    dry_run: bool = False,
) -> dict[str, Any]:
    project_root = Path(root).resolve()
    target = target_spec(platform_alias, python_version)
    requirements = resolve_profile_requirements(project_root, profile_names)
    executable = str(python_executable or sys.executable)
    wheelhouse = Path(wheelhouse_root).resolve() if wheelhouse_root else default_wheelhouse_root(project_root)
    stage = wheelhouse / f".download-{uuid.uuid4().hex}"
    input_lock = Path(lock_file).expanduser().resolve() if lock_file is not None else None
    if input_lock is not None:
        if not input_lock.is_file() or input_lock.is_symlink():
            raise DependencyStudioError(f"Release hash lock is missing or not a regular file: {input_lock}")
        command = build_locked_download_command(
            python_executable=executable, destination=stage, lock_file=input_lock, target=target
        )
    else:
        command = build_download_command(
            python_executable=executable, destination=stage, requirements=requirements, target=target
        )
    if dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "profiles": list(profile_names),
            "requirements": requirements,
            "target": target.to_dict(),
            "wheelhouse_root": str(wheelhouse),
            "release_lock_path": str(input_lock) if input_lock is not None else None,
            "release_lock_sha256": sha256_file(input_lock) if input_lock is not None else None,
            "command": command,
        }
    wheelhouse.mkdir(parents=True, exist_ok=True)
    stage.mkdir(parents=True, exist_ok=False)
    try:
        cp = subprocess.run(command, cwd=project_root, capture_output=True, text=True, encoding="utf-8",
                            errors="replace", timeout=max(30, int(timeout_seconds)), check=False)
        if cp.returncode:
            raise DependencyStudioError("pip download failed: " + (cp.stderr.strip() or cp.stdout.strip() or f"exit={cp.returncode}"))
        wheels = sorted(stage.glob("*.whl"))
        if not wheels:
            raise DependencyStudioError("pip download produced no wheel files")
        unexpected = [path.name for path in stage.iterdir() if path.is_file() and path.suffix.lower() != ".whl"]
        if unexpected:
            raise DependencyStudioError("Wheel-only download produced unexpected files: " + ", ".join(sorted(unexpected)))
        manifest = _manifest(
            project_root,
            profile_names,
            requirements,
            target,
            wheels,
            command,
            python_executable=executable,
            input_lock_path=input_lock,
        )
        lock_text = render_hash_lock(manifest["resolved_distributions"])
        if input_lock is not None:
            try:
                input_lock_text = input_lock.read_text(encoding="utf-8")
            except (OSError, UnicodeError) as exc:
                raise DependencyStudioError(f"Cannot read release hash lock {input_lock}: {exc}") from exc
            if input_lock_text != lock_text:
                raise DependencyStudioError(
                    "Resolved wheel inventory does not reproduce the canonical release hash lock"
                )
        lock_path = stage / LOCK_NAME
        lock_path.write_text(lock_text, encoding="utf-8")
        manifest["hash_lock_sha256"] = sha256_file(lock_path)
        slug = "+".join(re.sub(r"[^a-z0-9._+-]+", "-", profile.lower()) for profile in profile_names) or "default"
        name = f"{slug}__{target.alias}__py{target.python_version.replace('.', '')}__{manifest['resolution_fingerprint'][:12]}"
        manifest["bundle_name"] = name
        (stage / MANIFEST_NAME).write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        checked = verify_bundle(stage)
        if checked.get("ok") is not True:
            raise DependencyStudioError(f"Downloaded bundle verification failed: {checked.get('errors')}")
        destination = wheelhouse / name
        if destination.exists():
            existing = verify_bundle(destination)
            existing_manifest = read_manifest(destination / MANIFEST_NAME)
            if existing.get("ok") is True and existing_manifest and existing_manifest.get("resolution_fingerprint") == manifest.get("resolution_fingerprint") and existing_manifest.get("request_fingerprint") == manifest.get("request_fingerprint"):
                shutil.rmtree(stage)
                return {"ok": True, "state": "bundle_reused", "bundle_dir": str(destination), "manifest": existing_manifest, "verification": existing}
            raise DependencyStudioError(f"Immutable bundle path already exists with different contents: {destination}")
        os.replace(stage, destination)
        final = verify_bundle(destination)
        return {"ok": bool(final.get("ok")), "state": "bundle_downloaded", "bundle_dir": str(destination),
                "manifest": manifest, "verification": final, "pip_stdout_tail": cp.stdout.splitlines()[-20:]}
    finally:
        if stage.exists():
            shutil.rmtree(stage, ignore_errors=True)


def discover_bundles(root: Path | str, *, wheelhouse_root: Path | str | None = None,
                     required_profiles: Sequence[str] | None = None,
                     python_version: str | None = None, platform_alias: str | None = None,
                     verify: bool = True) -> list[dict[str, Any]]:
    project_root = Path(root).resolve()
    wheelhouse = Path(wheelhouse_root).resolve() if wheelhouse_root else default_wheelhouse_root(project_root)
    if not wheelhouse.is_dir():
        return []
    wanted_profiles = set(str(item) for item in (required_profiles or []))
    wanted_python = normalize_python_version(python_version) if python_version else None
    wanted_platform = target_spec(platform_alias, wanted_python).alias if platform_alias else None
    out: list[dict[str, Any]] = []
    for manifest_path in wheelhouse.glob(f"*/{MANIFEST_NAME}"):
        manifest = read_manifest(manifest_path)
        if not manifest or manifest.get("schema_version") != WHEELHOUSE_SCHEMA:
            continue
        coverage = set(str(item) for item in (manifest.get("resolved_profiles") or manifest.get("profiles") or []))
        target = _mapping(manifest.get("target"))
        if wanted_profiles and not wanted_profiles.issubset(coverage):
            continue
        if wanted_python and str(target.get("python_version") or "") != wanted_python:
            continue
        if wanted_platform and str(target.get("alias") or "") != wanted_platform:
            continue
        out.append({"bundle_dir": str(manifest_path.parent), "manifest_path": str(manifest_path), "manifest": manifest,
                    "verification": verify_bundle(manifest_path.parent) if verify else {"ok": None},
                    "created_at_utc": manifest.get("created_at_utc")})
    out.sort(key=lambda item: str(item.get("created_at_utc") or ""), reverse=True)
    return out
