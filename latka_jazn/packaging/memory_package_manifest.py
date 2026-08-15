from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any
import sqlite3
import uuid

from latka_jazn.core.package_integrity_manifest import sha256_file
from latka_jazn.core.version_source import read_runtime_version_from_version_py
from latka_jazn.version import version_number
from .memory_package_types import (
    MEMORY_FORMAT_VERSION, MEMORY_FORMAT_VERSION_V2, MEMORY_FORMAT_VERSION_V3,
    MEMORY_MANIFEST_SCHEMA_V1, MEMORY_MANIFEST_SCHEMA_V2, MEMORY_MANIFEST_SCHEMA_V3,
    MEMORY_PACKAGE_MANIFEST_PATH, MEMORY_RUNTIME_COMPATIBILITY_CONTRACT,
    TRANSIENT_DATABASE_SUFFIXES, TRUTH_BOUNDARY, inspect_sqlite_memory_file, read_json, sqlite_file,
)
from .memory_raw_segmentation import RawJsonlSegmenter, RawMemorySegmentationError


def verify_memory_package_manifest(
    package_root: Path, *, runtime_root: Path | None = None, require_runtime_match: bool = False,
) -> dict[str, Any]:
    package_root = Path(package_root).expanduser().resolve()
    runtime_root = Path(runtime_root).expanduser().resolve() if runtime_root else package_root
    manifest_path = package_root / MEMORY_PACKAGE_MANIFEST_PATH
    if not manifest_path.is_file():
        return {"ok": False, "status": "not_present", "errors": [{"code": "memory_package_manifest_missing"}], "warnings": []}
    payload = read_json(manifest_path)
    if payload is None:
        return {"ok": False, "status": "invalid", "errors": [{"code": "memory_package_manifest_invalid_json"}], "warnings": []}

    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    schema = str(payload.get("schema_version") or "").strip()
    if schema not in {MEMORY_MANIFEST_SCHEMA_V1, MEMORY_MANIFEST_SCHEMA_V2, MEMORY_MANIFEST_SCHEMA_V3}:
        errors.append({"code": "memory_package_manifest_schema_unsupported", "actual": schema or None})
    current_runtime = read_runtime_version_from_version_py(runtime_root)
    created_with_runtime: str | None = None
    runtime_version_match: bool | None = None
    compatibility_contract: str | None = None
    memory_format_version: Any = 1 if schema == MEMORY_MANIFEST_SCHEMA_V1 else payload.get("memory_format_version")

    if schema == MEMORY_MANIFEST_SCHEMA_V1:
        created_with_runtime = str(payload.get("runtime_version") or "").strip() or None
        if created_with_runtime and current_runtime:
            runtime_version_match = version_number(created_with_runtime) == version_number(current_runtime)
            if not runtime_version_match:
                row = {
                    "code": "memory_package_runtime_version_mismatch" if require_runtime_match else "legacy_memory_created_with_different_runtime",
                    "created_with_runtime": created_with_runtime, "current_runtime": current_runtime,
                }
                (errors if require_runtime_match else warnings).append(row)
    elif schema in {MEMORY_MANIFEST_SCHEMA_V2, MEMORY_MANIFEST_SCHEMA_V3}:
        expected_format = MEMORY_FORMAT_VERSION_V2 if schema == MEMORY_MANIFEST_SCHEMA_V2 else MEMORY_FORMAT_VERSION_V3
        if int(payload.get("memory_format_version", -1)) != expected_format:
            errors.append({"code": "memory_format_version_unsupported", "actual": payload.get("memory_format_version"), "expected": expected_format})
        try:
            uuid.UUID(str(payload.get("snapshot_id") or ""))
        except (ValueError, TypeError, AttributeError):
            errors.append({"code": "memory_snapshot_id_invalid"})
        created_at_text = str(payload.get("created_at_utc") or payload.get("generated_at_utc") or "").strip()
        try:
            created_at = datetime.fromisoformat(created_at_text.replace("Z", "+00:00"))
            if created_at.tzinfo is None:
                raise ValueError("timezone missing")
        except ValueError:
            errors.append({"code": "memory_snapshot_timestamp_invalid", "actual": created_at_text or None})
        created_with_runtime = str(payload.get("created_with_runtime") or "").strip() or None
        if not created_with_runtime:
            errors.append({"code": "memory_created_with_runtime_missing"})
        compatibility = payload.get("compatibility")
        if not isinstance(compatibility, dict):
            errors.append({"code": "memory_compatibility_contract_missing"})
        else:
            compatibility_contract = str(compatibility.get("contract") or "").strip() or None
            if compatibility_contract != MEMORY_RUNTIME_COMPATIBILITY_CONTRACT:
                errors.append({"code": "memory_compatibility_contract_unsupported", "actual": compatibility_contract})
            if compatibility.get("runtime_version_is_provenance_only") is not True:
                errors.append({"code": "memory_runtime_version_policy_invalid"})
        if created_with_runtime and current_runtime:
            runtime_version_match = version_number(created_with_runtime) == version_number(current_runtime)
            if not runtime_version_match:
                warnings.append({"code": "memory_created_with_different_runtime", "created_with_runtime": created_with_runtime, "current_runtime": current_runtime, "policy": "provenance_only"})

    files = payload.get("files")
    if not isinstance(files, list):
        errors.append({"code": "memory_package_files_invalid"}); files = []
    expected_paths: set[str] = set(); sqlite_paths: set[str] = set(); verified_count = 0
    for item in files:
        if not isinstance(item, dict):
            errors.append({"code": "memory_package_file_entry_invalid"}); continue
        relative = str(item.get("path") or "").replace("\\", "/").strip(); parts = Path(relative).parts
        if not relative or Path(relative).is_absolute() or ".." in parts or not relative.startswith("memory/"):
            errors.append({"code": "memory_package_path_unsafe", "path": relative}); continue
        if relative == MEMORY_PACKAGE_MANIFEST_PATH or relative in expected_paths:
            errors.append({"code": "memory_package_path_duplicate_or_self", "path": relative}); continue
        if relative.lower().endswith(TRANSIENT_DATABASE_SUFFIXES):
            errors.append({"code": "memory_package_transient_database_file", "path": relative}); continue
        expected_paths.add(relative)
        target = (package_root / Path(*relative.split("/"))).resolve()
        try: target.relative_to(package_root)
        except ValueError:
            errors.append({"code": "memory_package_path_escapes_root", "path": relative}); continue
        if not target.is_file():
            errors.append({"code": "memory_package_file_missing", "path": relative}); continue
        actual_size = target.stat().st_size; actual_sha = sha256_file(target)
        expected_size = int(item.get("size_bytes", -1)); expected_sha = str(item.get("sha256") or "").strip().lower()
        if actual_size != expected_size: errors.append({"code": "memory_package_file_size_mismatch", "path": relative})
        if actual_sha != expected_sha: errors.append({"code": "memory_package_file_sha256_mismatch", "path": relative})
        if actual_size == expected_size and actual_sha == expected_sha: verified_count += 1
        if sqlite_file(target): sqlite_paths.add(relative)

    memory_root = package_root / "memory"
    actual_paths = {p.relative_to(package_root).as_posix() for p in memory_root.rglob("*") if p.is_file() and p.resolve() != manifest_path.resolve()} if memory_root.is_dir() else set()
    for extra in sorted(actual_paths - expected_paths): errors.append({"code": "memory_package_unlisted_file", "path": extra})
    declared_count = int(payload.get("file_count", -1))
    if declared_count != len(expected_paths): errors.append({"code": "memory_package_file_count_mismatch", "declared": declared_count, "actual": len(expected_paths)})

    database_reports: list[dict[str, Any]] = []
    if schema in {MEMORY_MANIFEST_SCHEMA_V2, MEMORY_MANIFEST_SCHEMA_V3}:
        databases = payload.get("databases")
        if not isinstance(databases, list): errors.append({"code": "memory_database_manifest_invalid"}); databases = []
        declared: set[str] = set()
        for item in databases:
            if not isinstance(item, dict): errors.append({"code": "memory_database_entry_invalid"}); continue
            relative = str(item.get("path") or "").replace("\\", "/").strip()
            if relative in declared: errors.append({"code": "memory_database_entry_duplicate", "path": relative}); continue
            declared.add(relative)
            if relative not in expected_paths: errors.append({"code": "memory_database_not_in_files", "path": relative}); continue
            target = package_root / Path(*relative.split("/"))
            try: report = inspect_sqlite_memory_file(target)
            except (sqlite3.Error, OSError) as exc:
                errors.append({"code": "memory_database_validation_error", "path": relative, "error": f"{type(exc).__name__}: {exc}"}); continue
            report["relative_path"] = relative; database_reports.append(report)
            if report.get("ok") is not True: errors.append({"code": "memory_database_integrity_failed", "path": relative})
            for field in ("user_version", "application_id", "database_identity", "size_bytes", "sha256"):
                if field in item and item.get(field) != report.get(field): errors.append({"code": "memory_database_metadata_mismatch", "path": relative, "field": field})
            if item.get("snapshot_method") not in {"sqlite_backup_api", "sqlite_online_backup_api"}: errors.append({"code": "memory_database_snapshot_method_unsupported", "path": relative})
        for missing in sorted(sqlite_paths - declared): errors.append({"code": "memory_database_metadata_missing", "path": missing})
        for extra in sorted(declared - sqlite_paths): errors.append({"code": "memory_database_metadata_extra", "path": extra})
        if schema == MEMORY_MANIFEST_SCHEMA_V3:
            raw_segments = payload.get("raw_segments")
            if not isinstance(raw_segments, list):
                errors.append({"code": "memory_raw_segments_manifest_invalid"}); raw_segments = []
            materialized_sources: set[str] = set()
            for descriptor in raw_segments:
                if not isinstance(descriptor, dict):
                    errors.append({"code": "memory_raw_segment_descriptor_invalid"}); continue
                source_path = str(descriptor.get("source_path") or "").replace("\\", "/")
                if source_path in materialized_sources:
                    errors.append({"code": "memory_raw_segment_source_duplicate", "path": source_path}); continue
                materialized_sources.add(source_path)
                if source_path in expected_paths:
                    errors.append({"code": "memory_raw_segment_source_also_packaged", "path": source_path})
                segment_paths = {
                    str(item.get("package_path") or "").replace("\\", "/")
                    for item in descriptor.get("segments", []) if isinstance(item, dict)
                }
                for segment_path in sorted(segment_paths - expected_paths):
                    errors.append({"code": "memory_raw_segment_not_in_files", "path": segment_path})
                try:
                    RawJsonlSegmenter.verify_descriptor(package_root, descriptor)
                except (RawMemorySegmentationError, OSError, ValueError) as exc:
                    errors.append({
                        "code": "memory_raw_segment_verification_failed",
                        "path": source_path or None,
                        "error": f"{type(exc).__name__}: {exc}",
                    })
            member_limit = int(payload.get("package_member_limit_bytes") or 0)
            if member_limit < 1024 * 1024:
                errors.append({"code": "memory_package_member_limit_invalid", "actual": member_limit})
            elif any(
                isinstance(item, dict) and int(item.get("size_bytes") or 0) > member_limit
                for item in files
            ):
                errors.append({"code": "memory_package_member_limit_exceeded_by_manifest"})
    elif schema == MEMORY_MANIFEST_SCHEMA_V1:
        if sqlite_paths: warnings.append({"code": "legacy_memory_sqlite_snapshot_completeness_unverifiable", "policy": "quick_check_verified_but_original_wal_completeness_unknown"})
        for relative in sorted(sqlite_paths):
            try: report = inspect_sqlite_memory_file(package_root / Path(*relative.split("/")), legacy=True)
            except (sqlite3.Error, OSError) as exc:
                errors.append({"code": "legacy_memory_database_validation_error", "path": relative, "error": f"{type(exc).__name__}: {exc}"}); continue
            report["relative_path"] = relative; database_reports.append(report)
            if report.get("quick_check") != "ok": errors.append({"code": "legacy_memory_database_integrity_failed", "path": relative})

    return {
        "ok": not errors, "status": "verified" if not errors else "invalid", "manifest_path": str(manifest_path),
        "manifest_schema": schema, "memory_format_version": memory_format_version, "created_with_runtime": created_with_runtime,
        "current_runtime": current_runtime, "runtime_version_match": runtime_version_match,
        "runtime_version_is_provenance_only": schema in {MEMORY_MANIFEST_SCHEMA_V2, MEMORY_MANIFEST_SCHEMA_V3} or not require_runtime_match,
        "compatibility_contract": compatibility_contract, "declared_file_count": declared_count,
        "verified_file_count": verified_count, "sqlite_database_count": len(sqlite_paths), "database_reports": database_reports,
        "errors": errors, "warnings": warnings, "truth_boundary": TRUTH_BOUNDARY,
    }
