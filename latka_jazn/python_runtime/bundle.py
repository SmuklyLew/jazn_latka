from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import tempfile
from typing import Any, Mapping
import zipfile

from .contract import (
    RUNTIME_MANIFEST_NAME,
    RUNTIME_MANIFEST_SCHEMA,
    PythonRuntimeContractError,
    RuntimeTarget,
    runtime_target_from_mapping,
)

_CHUNK = 1024 * 1024
_BINARY_SUFFIXES = {".dll", ".exe", ".pyd", ".so", ".dylib", ".a", ".lib", ".zip", ".whl"}


def sha256_file(path: Path | str) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(_CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def safe_relative_path(value: str) -> str:
    raw = str(value or "")
    if not raw or "\\" in raw or "\x00" in raw:
        raise PythonRuntimeContractError(f"unsafe_runtime_member:{value!r}")
    path = PurePosixPath(raw)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise PythonRuntimeContractError(f"unsafe_runtime_member:{value!r}")
    if path.parts and ":" in path.parts[0]:
        raise PythonRuntimeContractError(f"unsafe_runtime_member:{value!r}")
    return path.as_posix()


def _zip_symlink(info: zipfile.ZipInfo) -> bool:
    mode = (int(info.external_attr) >> 16) & 0xFFFF
    return stat.S_ISLNK(mode)


def _zip_special(info: zipfile.ZipInfo) -> bool:
    if info.is_dir():
        return False
    mode = (int(info.external_attr) >> 16) & 0xFFFF
    file_type = stat.S_IFMT(mode) if mode else 0
    return file_type not in {0, stat.S_IFREG}


def _write_deterministic_member(
    archive: zipfile.ZipFile,
    name: str,
    payload: bytes,
    *,
    executable: bool = False,
) -> None:
    info = zipfile.ZipInfo(filename=name, date_time=(1980, 1, 1, 0, 0, 0))
    info.create_system = 3
    info.external_attr = ((0o100755 if executable else 0o100644) & 0xFFFF) << 16
    info.compress_type = (
        zipfile.ZIP_STORED if Path(name).suffix.lower() in _BINARY_SUFFIXES else zipfile.ZIP_DEFLATED
    )
    archive.writestr(info, payload, compress_type=info.compress_type, compresslevel=6)


def build_runtime_bundle(
    runtime_root: Path | str,
    output_zip: Path | str,
    *,
    target: RuntimeTarget,
    provider: str,
    interpreter_relative_path: str,
    packages_relative_path: str = "packages",
    source_reference: str | None = None,
) -> dict[str, Any]:
    root = Path(runtime_root).resolve()
    if not root.is_dir():
        raise PythonRuntimeContractError(f"runtime_root_missing:{root}")
    interpreter_rel = safe_relative_path(interpreter_relative_path)
    packages_rel = safe_relative_path(packages_relative_path)
    interpreter = root.joinpath(*PurePosixPath(interpreter_rel).parts)
    if not interpreter.is_file() or interpreter.is_symlink():
        raise PythonRuntimeContractError(f"runtime_interpreter_missing:{interpreter_rel}")

    rows: list[dict[str, Any]] = []
    payloads: list[tuple[str, bytes, bool]] = []
    for path in sorted(root.rglob("*")):
        if path.is_dir():
            if path.is_symlink():
                raise PythonRuntimeContractError(f"runtime_symlink_rejected:{path}")
            continue
        if path.is_symlink() or not stat.S_ISREG(path.lstat().st_mode):
            raise PythonRuntimeContractError(f"runtime_special_file_rejected:{path}")
        rel = safe_relative_path(path.relative_to(root).as_posix())
        if rel == RUNTIME_MANIFEST_NAME:
            continue
        data = path.read_bytes()
        executable = bool(path.stat().st_mode & stat.S_IXUSR) or rel == interpreter_rel
        rows.append(
            {
                "path": rel,
                "size_bytes": len(data),
                "sha256": _sha256_bytes(data),
                "executable": executable,
            }
        )
        payloads.append((rel, data, executable))

    if interpreter_rel not in {str(item["path"]) for item in rows}:
        raise PythonRuntimeContractError("runtime_interpreter_not_in_inventory")
    manifest: dict[str, Any] = {
        "schema_version": RUNTIME_MANIFEST_SCHEMA,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "provider": str(provider or "").strip() or "unknown",
        "source_reference": str(source_reference or "").strip() or None,
        "target": target.to_dict(),
        "interpreter_relative_path": interpreter_rel,
        "packages_relative_path": packages_rel,
        "file_count": len(rows),
        "files": rows,
        "isolation": {
            "isolated_mode_required": True,
            "ignore_python_environment": True,
            "ignore_user_site": True,
            "windows_pth_recommended": target.alias.startswith("windows-"),
        },
        "truth_boundary": (
            "The manifest proves the exact bytes of a prepared private Python runtime bundle. "
            "It does not claim upstream provenance beyond the recorded provider/source reference."
        ),
    }
    manifest_bytes = (
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")

    destination = Path(output_zip).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    tmp = destination.with_suffix(destination.suffix + ".tmp")
    tmp.unlink(missing_ok=True)
    with zipfile.ZipFile(tmp, "w", allowZip64=True) as archive:
        for rel, data, executable in payloads:
            _write_deterministic_member(archive, rel, data, executable=executable)
        _write_deterministic_member(archive, RUNTIME_MANIFEST_NAME, manifest_bytes)
    os.replace(tmp, destination)
    verification = verify_runtime_bundle(destination)
    if verification.get("ok") is not True:
        destination.unlink(missing_ok=True)
        raise PythonRuntimeContractError(
            f"built_runtime_bundle_failed_verification:{verification.get('errors')}"
        )
    return {
        "ok": True,
        "bundle": str(destination),
        "size_bytes": destination.stat().st_size,
        "sha256": sha256_file(destination),
        "manifest": manifest,
        "verification": verification,
    }


def verify_runtime_bundle(bundle_path: Path | str) -> dict[str, Any]:
    bundle = Path(bundle_path).resolve()
    errors: list[str] = []
    manifest: dict[str, Any] | None = None
    manifest_sha256: str | None = None
    target = None
    if not bundle.is_file() or bundle.is_symlink():
        return {"ok": False, "bundle": str(bundle), "errors": ["bundle_missing_or_symlink"]}
    try:
        with zipfile.ZipFile(bundle, "r") as archive:
            infos = archive.infolist()
            names: list[str] = []
            for info in infos:
                raw_name = info.filename.rstrip("/") if info.is_dir() else info.filename
                try:
                    name = safe_relative_path(raw_name)
                except PythonRuntimeContractError as exc:
                    errors.append(str(exc))
                    continue
                if name in names:
                    errors.append(f"duplicate_runtime_member:{name}")
                names.append(name)
                if _zip_symlink(info):
                    errors.append(f"runtime_symlink_rejected:{name}")
                if _zip_special(info):
                    errors.append(f"runtime_special_file_rejected:{name}")
            if RUNTIME_MANIFEST_NAME not in names:
                errors.append("runtime_manifest_missing")
            elif names.count(RUNTIME_MANIFEST_NAME) != 1:
                errors.append("runtime_manifest_duplicate")
            if errors:
                return {"ok": False, "bundle": str(bundle), "errors": errors}
            try:
                raw_manifest = archive.read(RUNTIME_MANIFEST_NAME)
                loaded = json.loads(raw_manifest.decode("utf-8"))
                manifest_sha256 = _sha256_bytes(raw_manifest)
            except (KeyError, UnicodeError, json.JSONDecodeError) as exc:
                return {
                    "ok": False,
                    "bundle": str(bundle),
                    "errors": [f"runtime_manifest_invalid:{type(exc).__name__}:{exc}"],
                }
            if not isinstance(loaded, dict):
                return {"ok": False, "bundle": str(bundle), "errors": ["runtime_manifest_not_object"]}
            manifest = loaded
            if manifest.get("schema_version") != RUNTIME_MANIFEST_SCHEMA:
                errors.append(f"unsupported_runtime_manifest_schema:{manifest.get('schema_version')!r}")
            try:
                target = runtime_target_from_mapping(
                    manifest.get("target") if isinstance(manifest.get("target"), Mapping) else {}
                )
            except PythonRuntimeContractError as exc:
                errors.append(str(exc))
            try:
                interpreter_rel = safe_relative_path(
                    str(manifest.get("interpreter_relative_path") or "")
                )
                packages_rel = safe_relative_path(str(manifest.get("packages_relative_path") or "packages"))
            except PythonRuntimeContractError as exc:
                errors.append(str(exc))
                interpreter_rel = ""
                packages_rel = ""

            raw_files = manifest.get("files")
            if not isinstance(raw_files, list):
                errors.append("runtime_manifest_files_invalid")
                raw_files = []
            expected: dict[str, Mapping[str, Any]] = {}
            for raw in raw_files:
                if not isinstance(raw, Mapping):
                    errors.append("runtime_manifest_file_entry_invalid")
                    continue
                try:
                    rel = safe_relative_path(str(raw.get("path") or ""))
                except PythonRuntimeContractError as exc:
                    errors.append(str(exc))
                    continue
                if rel in expected:
                    errors.append(f"runtime_manifest_duplicate_path:{rel}")
                expected[rel] = raw
            if manifest.get("file_count") != len(expected):
                errors.append("runtime_manifest_file_count_mismatch")
            actual_files = {
                safe_relative_path(info.filename)
                for info in infos
                if not info.is_dir() and info.filename != RUNTIME_MANIFEST_NAME
            }
            if actual_files != set(expected):
                missing = sorted(set(expected) - actual_files)
                extra = sorted(actual_files - set(expected))
                if missing:
                    errors.append(f"runtime_bundle_missing_files:{missing}")
                if extra:
                    errors.append(f"runtime_bundle_unlisted_files:{extra}")
            for rel, raw in expected.items():
                try:
                    payload = archive.read(rel)
                except KeyError:
                    continue
                if int(raw.get("size_bytes") or -1) != len(payload):
                    errors.append(f"runtime_size_mismatch:{rel}")
                if str(raw.get("sha256") or "").lower() != _sha256_bytes(payload):
                    errors.append(f"runtime_sha256_mismatch:{rel}")
            if interpreter_rel and interpreter_rel not in expected:
                errors.append("runtime_interpreter_not_in_inventory")
            if packages_rel and packages_rel == interpreter_rel:
                errors.append("runtime_packages_path_collides_with_interpreter")
            bad_crc = archive.testzip()
            if bad_crc:
                errors.append(f"runtime_zip_crc_failed:{bad_crc}")
    except (OSError, zipfile.BadZipFile) as exc:
        errors.append(f"runtime_bundle_unreadable:{type(exc).__name__}:{exc}")

    return {
        "ok": not errors,
        "bundle": str(bundle),
        "size_bytes": bundle.stat().st_size if bundle.is_file() else 0,
        "sha256": sha256_file(bundle) if bundle.is_file() else None,
        "manifest_sha256": manifest_sha256,
        "manifest": manifest,
        "target": target.to_dict() if target is not None else None,
        "errors": errors,
    }


def materialize_runtime_bundle(
    bundle_path: Path | str,
    materialized_root: Path | str,
) -> dict[str, Any]:
    bundle = Path(bundle_path).resolve()
    verification = verify_runtime_bundle(bundle)
    if verification.get("ok") is not True:
        raise PythonRuntimeContractError(
            f"runtime_bundle_not_verified:{verification.get('errors')}"
        )
    manifest = verification.get("manifest")
    if not isinstance(manifest, Mapping):
        raise PythonRuntimeContractError("runtime_manifest_missing_after_verification")
    target = runtime_target_from_mapping(
        manifest.get("target") if isinstance(manifest.get("target"), Mapping) else {}
    )
    outer_sha = str(verification.get("sha256") or "")
    base = Path(materialized_root).resolve()
    base.mkdir(parents=True, exist_ok=True)
    destination = base / f"{target.target_id}--{outer_sha[:12]}"
    ready_marker = destination / "JAZN_PYTHON_RUNTIME_READY.json"
    if ready_marker.is_file():
        try:
            ready = json.loads(ready_marker.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            ready = {}
        if ready.get("bundle_sha256") == outer_sha:
            interpreter = destination.joinpath(
                *PurePosixPath(str(manifest["interpreter_relative_path"])).parts
            )
            if interpreter.is_file():
                return {
                    "ok": True,
                    "state": "runtime_reused",
                    "runtime_root": str(destination),
                    "python_executable": str(interpreter),
                    "manifest": dict(manifest),
                    "bundle_sha256": outer_sha,
                }

    needed = sum(
        int(item.get("size_bytes") or 0)
        for item in manifest.get("files") or []
        if isinstance(item, Mapping)
    )
    free = shutil.disk_usage(base).free
    margin = max(64 * 1024 * 1024, int(needed * 0.05))
    if free < needed + margin:
        raise PythonRuntimeContractError(
            f"insufficient_runtime_materialization_space:{free}<{needed + margin}"
        )

    staging = Path(tempfile.mkdtemp(prefix=f".{target.target_id}.runtime-", dir=str(base)))
    try:
        with zipfile.ZipFile(bundle, "r") as archive:
            for info in archive.infolist():
                if info.is_dir():
                    continue
                rel = safe_relative_path(info.filename)
                target_path = staging.joinpath(*PurePosixPath(rel).parts)
                target_path.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info, "r") as source, target_path.open("xb") as output:
                    shutil.copyfileobj(source, output, length=_CHUNK)
                raw_mode = (int(info.external_attr) >> 16) & 0o777
                if raw_mode:
                    try:
                        target_path.chmod(raw_mode)
                    except OSError:
                        pass
        for raw in manifest.get("files") or []:
            if not isinstance(raw, Mapping):
                continue
            rel = safe_relative_path(str(raw.get("path") or ""))
            path = staging.joinpath(*PurePosixPath(rel).parts)
            if not path.is_file():
                raise PythonRuntimeContractError(f"materialized_runtime_file_missing:{rel}")
            if path.stat().st_size != int(raw.get("size_bytes") or -1):
                raise PythonRuntimeContractError(f"materialized_runtime_size_mismatch:{rel}")
            if sha256_file(path) != str(raw.get("sha256") or "").lower():
                raise PythonRuntimeContractError(f"materialized_runtime_sha256_mismatch:{rel}")
        marker = {
            "schema_version": "jazn_python_runtime_ready/v1",
            "bundle_sha256": outer_sha,
            "runtime_manifest_sha256": verification.get("manifest_sha256"),
            "target": target.to_dict(),
        }
        (staging / ready_marker.name).write_text(
            json.dumps(marker, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        if destination.exists():
            shutil.rmtree(destination)
        os.replace(staging, destination)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise

    interpreter = destination.joinpath(
        *PurePosixPath(str(manifest["interpreter_relative_path"])).parts
    )
    return {
        "ok": True,
        "state": "runtime_materialized",
        "runtime_root": str(destination),
        "python_executable": str(interpreter),
        "manifest": dict(manifest),
        "bundle_sha256": outer_sha,
    }
