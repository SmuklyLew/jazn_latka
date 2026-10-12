from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

PACKAGE_SET_SCHEMA = "jazn_package_set/v3"
SUPPORTED_PACKAGE_SET_SCHEMAS = frozenset({"jazn_package_set/v1", "jazn_package_set/v2", PACKAGE_SET_SCHEMA})
DEPENDENCY_SET_NAME = "JAZN_DEPENDENCY_SET.json"


class PackageSetContractError(ValueError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_package_set(path: Path | str) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise PackageSetContractError("package set must be a JSON object")
    schema = str(payload.get("schema_version") or "")
    if schema not in SUPPORTED_PACKAGE_SET_SCHEMAS:
        raise PackageSetContractError(f"unsupported package-set schema: {schema!r}")
    return payload


def build_v3_package_set(*, package_name: str, package_version: str, profile: str,
                         outputs: Iterable[Mapping[str, Any]], roles: Iterable[str] | None = None,
                         dependency_artifacts: Iterable[Mapping[str, Any]] | None = None,
                         generator: str | None = None, generator_version: str | None = None) -> dict[str, Any]:
    role_list = list(dict.fromkeys(str(item) for item in (roles or [profile]) if str(item)))
    if profile not in role_list:
        role_list.insert(0, profile)
    payload: dict[str, Any] = {
        "schema_version": PACKAGE_SET_SCHEMA,
        "package_name": package_name,
        "package_version": package_version,
        "profile": profile,
        "roles": role_list,
        "outputs": [dict(item) for item in outputs],
        "dependency_artifacts": [dict(item) for item in (dependency_artifacts or [])],
    }
    if generator:
        payload["generator"] = generator
    if generator_version:
        payload["generator_version"] = generator_version
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    payload["package_set_sha256"] = hashlib.sha256(canonical).hexdigest()
    return payload


def verify_output_hashes(base_dir: Path | str, payload: Mapping[str, Any]) -> list[str]:
    root = Path(base_dir).resolve()
    errors: list[str] = []
    for raw in payload.get("outputs") or []:
        if not isinstance(raw, Mapping):
            errors.append("invalid_output_entry")
            continue
        name = str(raw.get("filename") or "")
        if not name or Path(name).name != name:
            errors.append(f"unsafe_output_name:{name}")
            continue
        path = root / name
        if not path.is_file() or path.is_symlink():
            errors.append(f"missing_output:{name}")
            continue
        if int(raw.get("size_bytes") or -1) != path.stat().st_size:
            errors.append(f"size_mismatch:{name}")
        if str(raw.get("sha256") or "").lower() != sha256_file(path):
            errors.append(f"sha256_mismatch:{name}")
    return errors

def verify_package_set(base_dir: Path | str, payload: Mapping[str, Any]) -> list[str]:
    """Verify a package-set document and every referenced output fail-closed."""
    errors: list[str] = []
    schema = str(payload.get("schema_version") or "")
    if schema not in SUPPORTED_PACKAGE_SET_SCHEMAS:
        return [f"unsupported_schema:{schema}"]

    if schema == PACKAGE_SET_SCHEMA:
        declared_hash = str(payload.get("package_set_sha256") or "").lower()
        unsigned = dict(payload)
        unsigned.pop("package_set_sha256", None)
        canonical = json.dumps(
            unsigned, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        actual_hash = hashlib.sha256(canonical).hexdigest()
        if not declared_hash or declared_hash != actual_hash:
            errors.append("package_set_sha256_mismatch")

    errors.extend(verify_output_hashes(base_dir, payload))

    outputs_by_name: dict[str, Mapping[str, Any]] = {}
    for raw in payload.get("outputs") or []:
        if not isinstance(raw, Mapping):
            continue
        filename = str(raw.get("filename") or "")
        if filename:
            if filename in outputs_by_name:
                errors.append(f"duplicate_output:{filename}")
            outputs_by_name[filename] = raw

    roles = {str(item) for item in payload.get("roles") or [] if str(item)}
    if schema == PACKAGE_SET_SCHEMA and not roles:
        errors.append("roles_missing")

    dependency_entries = payload.get("dependency_artifacts") or []
    if dependency_entries and "dependencies" not in roles:
        errors.append("dependency_role_missing")
    for raw in dependency_entries:
        if not isinstance(raw, Mapping):
            errors.append("invalid_dependency_artifact_entry")
            continue
        filename = str(raw.get("filename") or "")
        if not filename or Path(filename).name != filename:
            errors.append(f"unsafe_dependency_artifact_name:{filename}")
            continue
        output = outputs_by_name.get(filename)
        if output is None:
            errors.append(f"dependency_artifact_not_in_outputs:{filename}")
            continue
        if str(output.get("role") or "") != "dependencies":
            errors.append(f"dependency_artifact_role_mismatch:{filename}")
        if str(output.get("sha256") or "").lower() != str(raw.get("sha256") or "").lower():
            errors.append(f"dependency_artifact_sha256_mismatch:{filename}")
        if raw.get("size_bytes") is not None and int(output.get("size_bytes") or -1) != int(raw.get("size_bytes") or -2):
            errors.append(f"dependency_artifact_size_mismatch:{filename}")
    return errors
