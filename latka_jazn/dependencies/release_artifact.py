from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Mapping

from .common import DEPENDENCY_SET_NAME, default_wheelhouse_root, target_spec


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _candidate_source_dirs(root: Path) -> list[Path]:
    raw = os.environ.get("JAZN_PACKAGE_SOURCE_DIR")
    candidates = [Path(raw).expanduser().resolve()] if raw else []
    candidates += [root, root.parent]
    out: list[Path] = []
    for item in candidates:
        if item not in out:
            out.append(item)
    return out


def load_dependency_set(root: Path | str) -> tuple[Path | None, dict[str, Any] | None]:
    project_root = Path(root).resolve()
    for directory in _candidate_source_dirs(project_root):
        path = directory / DEPENDENCY_SET_NAME
        if not path.is_file():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict) and payload.get("schema_version") == "jazn_dependency_set/v1":
            return path, payload
    return None, None



def _verified_package_set_for_dependency_set(
    project_root: Path,
    dependency_set: dict[str, Any],
) -> tuple[Path | None, dict[str, Any] | None, list[dict[str, Any]]]:
    """Find a package-set that cryptographically binds the dependency projection."""
    try:
        from latka_jazn.packaging.package_set_contract import read_package_set, verify_package_set
    except ImportError as exc:
        return None, None, [{"reason": "package_set_contract_unavailable", "detail": str(exc)}]

    expected = dependency_set.get("artifacts") if isinstance(dependency_set.get("artifacts"), list) else []
    rejected: list[dict[str, Any]] = []
    for directory in _candidate_source_dirs(project_root):
        if not directory.is_dir():
            continue
        for candidate in sorted(directory.glob("*.package.json")):
            try:
                package_set = read_package_set(candidate)
            except (OSError, UnicodeError, ValueError) as exc:
                rejected.append({"path": str(candidate), "reason": f"package_set_unreadable:{type(exc).__name__}:{exc}"})
                continue
            errors = verify_package_set(directory, package_set)
            if errors:
                rejected.append({"path": str(candidate), "reason": "package_set_verification_failed", "errors": errors})
                continue
            projected = package_set.get("dependency_artifacts") if isinstance(package_set.get("dependency_artifacts"), list) else []
            if projected != expected:
                rejected.append({"path": str(candidate), "reason": "dependency_set_projection_mismatch"})
                continue
            return candidate, package_set, rejected
    return None, None, rejected

def materialize_compatible_dependency_artifact(root: Path | str) -> dict[str, Any]:
    project_root = Path(root).resolve()
    set_path, payload = load_dependency_set(project_root)
    if payload is None or set_path is None:
        return {"ok": False, "state": "dependency_set_missing", "searched": [str(p) for p in _candidate_source_dirs(project_root)]}
    package_set_path, package_set, package_set_rejections = _verified_package_set_for_dependency_set(project_root, payload)
    if package_set_path is None or package_set is None:
        return {
            "ok": False,
            "state": "dependency_package_set_unverified",
            "dependency_set_path": str(set_path),
            "searched": [str(p) for p in _candidate_source_dirs(project_root)],
            "package_set_rejections": package_set_rejections,
        }
    current = target_spec("current", None)
    wanted = current.to_dict()
    entries = _list(payload.get("artifacts"))
    source_dir = set_path.parent
    rejections: list[dict[str, Any]] = []
    for raw in entries:
        if not isinstance(raw, dict):
            continue
        target = _mapping(raw.get("target"))
        identity_fields = (
            "alias",
            "python_version",
            "implementation",
            "abi",
            "platform_family",
            "architecture",
            "libc_family",
        )
        if any(
            str(target.get(field) or "") != str(wanted.get(field) or "")
            for field in identity_fields
            if wanted.get(field) not in (None, "")
        ):
            continue
        name = str(raw.get("filename") or "")
        if not name or Path(name).name != name:
            rejections.append({"filename": name, "reason": "unsafe_filename"})
            continue
        source_candidates = [source_dir, *_candidate_source_dirs(project_root)]
        source: Path | None = None
        for candidate_dir in source_candidates:
            candidate = candidate_dir / name
            if candidate.is_file() and not candidate.is_symlink():
                source = candidate
                break
        if source is None:
            rejections.append({
                "filename": name,
                "reason": "missing",
                "searched": [str(directory / name) for directory in source_candidates],
            })
            continue
        bundle_name = str(raw.get("bundle_name") or Path(name).stem)
        destination = default_wheelhouse_root(project_root) / bundle_name
        try:
            from latka_jazn.packaging.dependency_package_contract import extract_verified_dependency_sidecar
            result = extract_verified_dependency_sidecar(
                source,
                destination,
                expected_sha256=str(raw.get("sha256") or "") or None,
                expected_target=wanted,
            )
        except Exception as exc:
            rejections.append({"filename": name, "reason": f"{type(exc).__name__}:{exc}"})
            continue
        result["dependency_set_path"] = str(set_path)
        result["package_set_path"] = str(package_set_path)
        result["package_set_schema_version"] = package_set.get("schema_version")
        result["artifact"] = raw
        return result
    return {
        "ok": False,
        "state": "no_compatible_verified_dependency_bundle",
        "dependency_set_path": str(set_path),
        "package_set_path": str(package_set_path),
        "target": wanted,
        "rejections": rejections,
    }
