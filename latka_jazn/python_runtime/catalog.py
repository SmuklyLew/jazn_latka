from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from .bundle import sha256_file, verify_runtime_bundle
from .contract import (
    DEFAULT_PYTHON_PREFERENCE,
    RUNTIME_INDEX_NAME,
    RUNTIME_SET_NAME,
    RUNTIME_SET_SCHEMA,
    HostTarget,
    PythonRuntimeContractError,
    detect_host_target,
    python_preference,
    runtime_target_from_mapping,
    target_matches_host,
)


def build_runtime_set(bundle_paths: Sequence[Path | str]) -> dict[str, Any]:
    artifacts: list[dict[str, Any]] = []
    seen_targets: set[str] = set()
    for raw in bundle_paths:
        bundle = Path(raw).resolve()
        verification = verify_runtime_bundle(bundle)
        if verification.get("ok") is not True:
            raise PythonRuntimeContractError(
                f"runtime_bundle_not_verified:{bundle}:{verification.get('errors')}"
            )
        manifest = verification.get("manifest")
        if not isinstance(manifest, Mapping):
            raise PythonRuntimeContractError(f"runtime_manifest_missing:{bundle}")
        target = runtime_target_from_mapping(
            manifest.get("target") if isinstance(manifest.get("target"), Mapping) else {}
        )
        if target.target_id in seen_targets:
            raise PythonRuntimeContractError(f"duplicate_runtime_target:{target.target_id}")
        seen_targets.add(target.target_id)
        artifacts.append(
            {
                "role": "python-runtime",
                "target_id": target.target_id,
                "filename": bundle.name,
                "size_bytes": bundle.stat().st_size,
                "sha256": str(verification.get("sha256") or ""),
                "runtime_manifest_sha256": str(verification.get("manifest_sha256") or ""),
                "target": target.to_dict(),
                "provider": str(manifest.get("provider") or ""),
                "interpreter_relative_path": str(manifest.get("interpreter_relative_path") or ""),
                "packages_relative_path": str(manifest.get("packages_relative_path") or "packages"),
            }
        )
    artifacts.sort(
        key=lambda item: (
            str((item.get("target") or {}).get("alias") or ""),
            str((item.get("target") or {}).get("libc_family") or ""),
            str((item.get("target") or {}).get("python_version") or ""),
        )
    )
    return {
        "schema_version": RUNTIME_SET_SCHEMA,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "artifacts": artifacts,
        "python_preference": list(DEFAULT_PYTHON_PREFERENCE),
        "network_fallback_allowed": False,
        "selection_contract": (
            "Select only an outer-SHA-verified artifact matching host OS/architecture and, on Linux, libc. "
            "Prefer the configured CPython minor order; filename alone is never authoritative."
        ),
    }


def load_runtime_set(path: Path | str) -> dict[str, Any]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PythonRuntimeContractError(f"runtime_set_unreadable:{exc}") from exc
    if not isinstance(payload, dict):
        raise PythonRuntimeContractError("runtime_set_not_object")
    if payload.get("schema_version") != RUNTIME_SET_SCHEMA:
        raise PythonRuntimeContractError(
            f"unsupported_runtime_set_schema:{payload.get('schema_version')!r}"
        )
    return payload


def render_runtime_index(payload: Mapping[str, Any]) -> str:
    if payload.get("schema_version") != RUNTIME_SET_SCHEMA:
        raise PythonRuntimeContractError("runtime_index_requires_v1_runtime_set")
    header = (
        "target_id\talias\tpython_version\tlibc_family\tfilename\tsha256\t"
        "interpreter_relative_path\tpackages_relative_path"
    )
    lines = [header]
    for raw in payload.get("artifacts") or []:
        if not isinstance(raw, Mapping):
            raise PythonRuntimeContractError("runtime_set_artifact_invalid")
        target = runtime_target_from_mapping(
            raw.get("target") if isinstance(raw.get("target"), Mapping) else {}
        )
        values = (
            str(raw.get("target_id") or target.target_id),
            target.alias,
            target.python_version,
            target.libc_family,
            str(raw.get("filename") or ""),
            str(raw.get("sha256") or ""),
            str(raw.get("interpreter_relative_path") or ""),
            str(raw.get("packages_relative_path") or "packages"),
        )
        if any("\t" in value or "\n" in value or "\r" in value for value in values):
            raise PythonRuntimeContractError("runtime_index_field_contains_control_separator")
        lines.append("\t".join(values))
    return "\n".join(lines) + "\n"


def write_runtime_set(
    output_dir: Path | str,
    bundle_paths: Sequence[Path | str],
) -> dict[str, Any]:
    destination = Path(output_dir).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    payload = build_runtime_set(bundle_paths)
    set_path = destination / RUNTIME_SET_NAME
    index_path = destination / RUNTIME_INDEX_NAME
    set_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    index_path.write_text(render_runtime_index(payload), encoding="utf-8")
    return {
        "ok": True,
        "runtime_set_path": str(set_path),
        "runtime_index_path": str(index_path),
        "runtime_set": payload,
    }


def verify_runtime_set(
    base_dir: Path | str,
    payload: Mapping[str, Any],
    *,
    verify_bundles: bool = True,
) -> dict[str, Any]:
    root = Path(base_dir).resolve()
    errors: list[str] = []
    if payload.get("schema_version") != RUNTIME_SET_SCHEMA:
        return {"ok": False, "errors": ["unsupported_runtime_set_schema"]}
    seen_targets: set[str] = set()
    seen_files: set[str] = set()
    for raw in payload.get("artifacts") or []:
        if not isinstance(raw, Mapping):
            errors.append("runtime_set_artifact_invalid")
            continue
        filename = str(raw.get("filename") or "")
        if not filename or Path(filename).name != filename:
            errors.append(f"runtime_set_unsafe_filename:{filename}")
            continue
        try:
            target = runtime_target_from_mapping(
                raw.get("target") if isinstance(raw.get("target"), Mapping) else {}
            )
        except PythonRuntimeContractError as exc:
            errors.append(str(exc))
            continue
        target_id = str(raw.get("target_id") or "")
        if target_id != target.target_id:
            errors.append(f"runtime_set_target_id_mismatch:{target_id}!={target.target_id}")
        if target.target_id in seen_targets:
            errors.append(f"runtime_set_duplicate_target:{target.target_id}")
        seen_targets.add(target.target_id)
        if filename in seen_files:
            errors.append(f"runtime_set_duplicate_filename:{filename}")
        seen_files.add(filename)
        path = root / filename
        if not path.is_file() or path.is_symlink():
            errors.append(f"runtime_set_missing_artifact:{filename}")
            continue
        if int(raw.get("size_bytes") or -1) != path.stat().st_size:
            errors.append(f"runtime_set_size_mismatch:{filename}")
        if str(raw.get("sha256") or "").lower() != sha256_file(path):
            errors.append(f"runtime_set_sha256_mismatch:{filename}")
        if verify_bundles:
            verification = verify_runtime_bundle(path)
            if verification.get("ok") is not True:
                errors.append(f"runtime_set_bundle_invalid:{filename}:{verification.get('errors')}")
            elif verification.get("target") != target.to_dict():
                errors.append(f"runtime_set_bundle_target_mismatch:{filename}")
    return {"ok": not errors, "errors": errors, "artifact_count": len(seen_files)}


def select_runtime_artifact(
    payload: Mapping[str, Any],
    *,
    host: HostTarget | None = None,
    requested_python: str | None = None,
    preference: Sequence[str] | None = None,
) -> dict[str, Any]:
    if payload.get("schema_version") != RUNTIME_SET_SCHEMA:
        raise PythonRuntimeContractError("unsupported_runtime_set_schema")
    resolved_host = host or detect_host_target()
    raw_preference = preference or tuple(
        str(item) for item in payload.get("python_preference") or DEFAULT_PYTHON_PREFERENCE
    )
    order = python_preference(requested_python, raw_preference)
    candidates: list[tuple[int, str, dict[str, Any]]] = []
    for raw in payload.get("artifacts") or []:
        if not isinstance(raw, Mapping):
            continue
        try:
            target = runtime_target_from_mapping(
                raw.get("target") if isinstance(raw.get("target"), Mapping) else {}
            )
        except PythonRuntimeContractError:
            continue
        if not target_matches_host(target, resolved_host):
            continue
        if target.python_version not in order:
            continue
        candidates.append((order.index(target.python_version), str(raw.get("filename") or ""), dict(raw)))
    if not candidates:
        raise PythonRuntimeContractError(
            f"no_compatible_python_runtime:host={resolved_host.to_dict()}:preference={list(order)}"
        )
    candidates.sort(key=lambda item: (item[0], item[1]))
    selected = candidates[0][2]
    selected["selection"] = {
        "host": resolved_host.to_dict(),
        "python_preference": list(order),
        "reason": "highest_preferred_verified-compatible runtime target",
    }
    return selected
