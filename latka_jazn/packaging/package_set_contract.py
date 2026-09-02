from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping
import hashlib
import json
import re

from latka_jazn.tools.safe_paths import validate_safe_relative_path, validate_safe_path_set

CURRENT_SCHEMA = "jazn_package_set/v3"
READABLE_SCHEMAS = frozenset({"jazn_package_set/v1", "jazn_package_set/v2", CURRENT_SCHEMA})
WRITABLE_SCHEMAS = frozenset({CURRENT_SCHEMA})
CONTENT_PROFILES = frozenset({"system", "memory", "combined", "dependencies"})
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")


class PackageSetContractError(ValueError):
    pass


def _flat_filename(value: object) -> str:
    raw = str(value or "").strip()
    canonical = validate_safe_relative_path(raw)
    if "/" in canonical:
        raise PackageSetContractError(f"package output filename must be flat: {raw!r}")
    return canonical


def _sha(value: object, *, required: bool = True) -> str | None:
    raw = str(value or "").strip().lower()
    if not raw and not required:
        return None
    if not _SHA_RE.fullmatch(raw):
        raise PackageSetContractError(f"invalid SHA-256: {value!r}")
    return raw


def package_set_hash(outputs: Iterable[Mapping[str, Any]]) -> str:
    digest = hashlib.sha256()
    rows = sorted(outputs, key=lambda row: int(row.get("part_no", 0)))
    for row in rows:
        digest.update(
            f"{int(row.get('part_no', 0))}\0{row.get('filename')}\0{int(row.get('size_bytes', 0))}\0{row.get('sha256')}\n".encode("utf-8")
        )
    return digest.hexdigest()


def plan_hash(entries: Iterable[Mapping[str, Any]], *, profile: str) -> str:
    rows = [
        {
            "path": validate_safe_relative_path(str(item.get("path") or "")),
            "size_bytes": int(item.get("size_bytes", 0)),
            "sha256": _sha(item.get("sha256")),
            "classification": str(item.get("classification") or "file"),
        }
        for item in entries
    ]
    rows.sort(key=lambda item: item["path"])
    raw = json.dumps({"profile": profile, "entries": rows}, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def validate_package_set(payload: Mapping[str, Any], *, require_current: bool = False) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise PackageSetContractError("package sidecar root must be an object")
    schema = str(payload.get("schema_version") or "").strip()
    allowed = WRITABLE_SCHEMAS if require_current else READABLE_SCHEMAS
    if schema not in allowed:
        raise PackageSetContractError(f"unsupported package-set schema: {schema!r}")
    package_name = _flat_filename(payload.get("package_name"))
    profile = str(payload.get("profile") or "unknown").strip().lower()
    if schema == CURRENT_SCHEMA and profile not in CONTENT_PROFILES:
        raise PackageSetContractError(f"unsupported v3 package profile: {profile!r}")
    archive_format = str(payload.get("archive_format") or "").strip().lower()
    if archive_format not in {"binary", "independent"}:
        raise PackageSetContractError(f"unsupported archive_format: {archive_format!r}")
    raw_outputs = payload.get("outputs")
    if not isinstance(raw_outputs, list) or not raw_outputs:
        raise PackageSetContractError("package sidecar requires non-empty outputs")
    outputs: list[dict[str, Any]] = []
    names: list[str] = []
    part_numbers: set[int] = set()
    for raw in raw_outputs:
        if not isinstance(raw, Mapping):
            raise PackageSetContractError("package output entry must be an object")
        part_no = int(raw.get("part_no", len(outputs) + 1))
        if part_no < 1 or part_no in part_numbers:
            raise PackageSetContractError("package output part numbers must be positive and unique")
        part_numbers.add(part_no)
        filename = _flat_filename(raw.get("filename"))
        names.append(filename)
        size = int(raw.get("size_bytes", -1))
        if size < 0:
            raise PackageSetContractError(f"negative package output size: {filename}")
        outputs.append({
            **dict(raw), "part_no": part_no, "filename": filename,
            "size_bytes": size, "sha256": _sha(raw.get("sha256")),
        })
    validate_safe_path_set(names)
    result = dict(payload)
    result.update({
        "schema_version": schema,
        "package_name": package_name,
        "profile": profile,
        "archive_format": archive_format,
        "outputs": sorted(outputs, key=lambda item: item["part_no"]),
    })
    if schema == CURRENT_SCHEMA:
        entries = payload.get("entries")
        if not isinstance(entries, list):
            raise PackageSetContractError("v3 package sidecar requires entries inventory")
        paths = [validate_safe_relative_path(str((item or {}).get("path") or "")) for item in entries if isinstance(item, Mapping)]
        if len(paths) != len(entries):
            raise PackageSetContractError("v3 package entries must be objects")
        validate_safe_path_set(paths)
        declared_plan = _sha(payload.get("plan_sha256"))
        computed_plan = plan_hash(entries, profile=profile)
        if declared_plan != computed_plan:
            raise PackageSetContractError("v3 plan_sha256 does not match entries")
        declared_set = _sha(payload.get("package_set_sha256"))
        if declared_set != package_set_hash(outputs):
            raise PackageSetContractError("v3 package_set_sha256 does not match outputs")
    return result


def load_package_set(path: Path | str, *, require_current: bool = False) -> dict[str, Any]:
    source = Path(path)
    try:
        payload = json.loads(source.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PackageSetContractError(f"cannot read package sidecar {source}: {exc}") from exc
    return validate_package_set(payload, require_current=require_current)


def build_single_zip_sidecar(
    *,
    package_name: str,
    profile: str,
    package_version: str,
    zip_path: Path,
    entries: list[dict[str, Any]],
    artifact_role: str | None = None,
    related_artifacts: list[dict[str, Any]] | None = None,
    generator: str = "latka_jazn",
) -> dict[str, Any]:
    zip_path = Path(zip_path)
    digest = hashlib.sha256()
    with zip_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    output = {
        "part_no": 1,
        "filename": zip_path.name,
        "size_bytes": zip_path.stat().st_size,
        "sha256": digest.hexdigest(),
        "is_complete_zip": True,
    }
    payload: dict[str, Any] = {
        "schema_version": CURRENT_SCHEMA,
        "generator": generator,
        "package_name": _flat_filename(package_name),
        "profile": profile,
        "archive_format": "independent",
        "container_format": "zip",
        "package_version": package_version,
        "plan_sha256": plan_hash(entries, profile=profile),
        "entry_count": len(entries),
        "source_total_size_bytes": sum(int(item.get("size_bytes", 0)) for item in entries),
        "package_set_sha256": package_set_hash([output]),
        "outputs": [output],
        "entries": entries,
        "artifact_role": artifact_role or profile,
        "related_artifacts": list(related_artifacts or []),
    }
    return validate_package_set(payload, require_current=True)


__all__ = [
    "CURRENT_SCHEMA", "READABLE_SCHEMAS", "WRITABLE_SCHEMAS", "CONTENT_PROFILES",
    "PackageSetContractError", "build_single_zip_sidecar", "load_package_set",
    "package_set_hash", "plan_hash", "validate_package_set",
]
