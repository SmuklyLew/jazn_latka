from __future__ import annotations

import errno
import hashlib
import json
import os
import shutil
import sqlite3
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from latka_jazn.config import JaznConfig
from latka_jazn.core.package_integrity_manifest import sha256_file
from latka_jazn.core.runtime_daemon import status_daemon
from latka_jazn.core.source_provenance import read_source_provenance
from latka_jazn.core.version_source import read_runtime_version_from_version_py
from latka_jazn.packaging.split_zip_package import (
    extract_independent_zip_set_resumable,
    extract_joined_zip_resumable,
    infer_base_zip_name,
    join_split_package_to_zip,
    load_package_expectations,
    load_package_set_metadata,
    resolve_renamed_package_parts,
    test_joined_zip,
    verify_extracted_zip_set,
    verify_extracted_zip_tree,
)
from latka_jazn.tools.package_integrity import verify_package_integrity_manifest
from latka_jazn.version import schema_version, version_number

MEMORY_PACKAGE_MANIFEST_PATH = "memory/MEMORY_PACKAGE_MANIFEST.json"
MEMORY_MANIFEST_SCHEMA_V1 = "jazn_memory_package_manifest/v1"
MEMORY_MANIFEST_SCHEMA_V2 = "jazn_memory_package_manifest/v2"
MEMORY_FORMAT_VERSION = 2
MEMORY_RUNTIME_COMPATIBILITY_CONTRACT = "jazn_memory_runtime/v1"
SUPPORTED_MEMORY_MANIFEST_SCHEMAS = frozenset(
    {MEMORY_MANIFEST_SCHEMA_V1, MEMORY_MANIFEST_SCHEMA_V2}
)
SQLITE_HEADER = b"SQLite format 3\x00"
ATTACH_SCHEMA_VERSION = schema_version("memory_package_attach")
ATTACH_MARKER_PATH = "workspace_runtime/MEMORY_ATTACH_CURRENT.json"
TRANSIENT_DATABASE_SUFFIXES = ("-wal", "-shm", ".sqlite-wal", ".sqlite-shm", ".sqlite3-wal", ".sqlite3-shm", ".db-wal", ".db-shm")
VERIFIED_PROVENANCE_STATES = {
    "clean_checkout_verified",
    "development_dirty_verified",
    "verified_export_without_git_history",
}

TRUTH_BOUNDARY = (
    "A memory package is data, never an active runtime root. Package verification proves archive/file integrity "
    "and SQLite structural health only. created_with_runtime is provenance, not an equality gate. L2/L3 truth "
    "status and identity claims are not promoted by packaging or attachment."
)


@dataclass(slots=True)
class MemoryAttachResult:
    ok: bool
    state: str
    runtime_root: str
    report: dict[str, Any]
    pending: bool = False
    exit_code: int = 0
    schema_version: str = ATTACH_SCHEMA_VERSION
    truth_boundary: str = TRUTH_BOUNDARY

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        return payload if isinstance(payload, dict) else None
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError):
        return None


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".tmp-{uuid.uuid4().hex}")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _iso_datetime_valid(value: Any) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None


def _uuid_valid(value: Any) -> bool:
    try:
        uuid.UUID(str(value or ""))
        return True
    except (ValueError, AttributeError, TypeError):
        return False


def _sqlite_file(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            return handle.read(len(SQLITE_HEADER)) == SQLITE_HEADER
    except OSError:
        return False


def _sqlite_schema_sha256(connection: sqlite3.Connection) -> str:
    rows = connection.execute(
        "SELECT type,name,tbl_name,COALESCE(sql,'') FROM sqlite_schema "
        "WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name,tbl_name"
    ).fetchall()
    raw = json.dumps([list(row) for row in rows], ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def inspect_sqlite_memory_file(path: Path) -> dict[str, Any]:
    path = Path(path).resolve()
    uri = path.as_uri() + "?mode=ro"
    with sqlite3.connect(uri, uri=True, timeout=30.0) as connection:
        connection.execute("PRAGMA query_only=ON")
        connection.execute("PRAGMA busy_timeout=30000")
        integrity = [str(row[0]) for row in connection.execute("PRAGMA integrity_check").fetchall()]
        foreign = [tuple(row) for row in connection.execute("PRAGMA foreign_key_check").fetchall()]
        user_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        application_id = int(connection.execute("PRAGMA application_id").fetchone()[0])
        schema_sha256 = _sqlite_schema_sha256(connection)
        table_count = int(
            connection.execute("SELECT COUNT(*) FROM sqlite_schema WHERE type='table'").fetchone()[0]
        )
    return {
        "ok": integrity == ["ok"] and not foreign,
        "path": str(path),
        "size_bytes": path.stat().st_size,
        "sha256": sha256_file(path),
        "integrity_check": integrity,
        "foreign_key_error_count": len(foreign),
        "foreign_key_errors": foreign[:20],
        "user_version": user_version,
        "application_id": application_id,
        "schema_sha256": schema_sha256,
        "table_count": table_count,
    }


def _runtime_installation_status(root: Path) -> dict[str, Any]:
    root = Path(root).expanduser().resolve()
    version = read_runtime_version_from_version_py(root)
    manifest = verify_package_integrity_manifest(root) if (root / "PACKAGE_INTEGRITY_MANIFEST.json").is_file() else {"ok": False, "errors": [{"code": "manifest_missing"}]}
    provenance = read_source_provenance(root, profile="system_smoke").to_dict()
    start_file = next((name for name in ("run.py", "main.py") if (root / name).is_file()), None)
    structure_ok = bool(version and start_file and (root / "latka_jazn").is_dir())
    provenance_ok = provenance.get("status") in VERIFIED_PROVENANCE_STATES
    return {
        "ok": bool(structure_ok and manifest.get("ok") is True and provenance_ok),
        "root": str(root),
        "version": version,
        "start_file": start_file,
        "structure_ok": structure_ok,
        "manifest_ok": manifest.get("ok") is True,
        "manifest": manifest,
        "provenance_ok": provenance_ok,
        "provenance": provenance,
    }


def verify_memory_package_manifest(
    package_root: Path,
    *,
    runtime_root: Path | None = None,
) -> dict[str, Any]:
    package_root = Path(package_root).expanduser().resolve()
    runtime_root = Path(runtime_root).expanduser().resolve() if runtime_root is not None else package_root
    manifest_path = package_root / MEMORY_PACKAGE_MANIFEST_PATH
    if not manifest_path.is_file():
        return {
            "ok": False,
            "status": "not_present",
            "manifest_path": str(manifest_path),
            "errors": [{"code": "memory_package_manifest_missing"}],
            "warnings": [],
            "truth_boundary": TRUTH_BOUNDARY,
        }
    payload = _read_json(manifest_path)
    if not isinstance(payload, dict):
        return {
            "ok": False,
            "status": "invalid",
            "manifest_path": str(manifest_path),
            "errors": [{"code": "memory_package_manifest_invalid_json"}],
            "warnings": [],
            "truth_boundary": TRUTH_BOUNDARY,
        }

    schema = str(payload.get("schema_version") or "").strip()
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    if schema not in SUPPORTED_MEMORY_MANIFEST_SCHEMAS:
        errors.append({"code": "memory_package_manifest_schema_unsupported", "actual": schema or None})

    current_runtime = read_runtime_version_from_version_py(runtime_root)
    created_with_runtime: str | None = None
    compatibility_contract: str | None = None
    runtime_version_match: bool | None = None

    if schema == MEMORY_MANIFEST_SCHEMA_V1:
        created_with_runtime = str(payload.get("runtime_version") or "").strip() or None
        if created_with_runtime and current_runtime:
            runtime_version_match = version_number(created_with_runtime) == version_number(current_runtime)
            if not runtime_version_match:
                warnings.append(
                    {
                        "code": "legacy_memory_created_with_different_runtime",
                        "created_with_runtime": created_with_runtime,
                        "current_runtime": current_runtime,
                        "policy": "advisory_only_under_v2_loader",
                    }
                )
        else:
            warnings.append(
                {
                    "code": "legacy_memory_runtime_provenance_incomplete",
                    "created_with_runtime": created_with_runtime,
                    "current_runtime": current_runtime,
                }
            )
    elif schema == MEMORY_MANIFEST_SCHEMA_V2:
        if int(payload.get("memory_format_version", -1)) != MEMORY_FORMAT_VERSION:
            errors.append(
                {
                    "code": "memory_format_version_unsupported",
                    "actual": payload.get("memory_format_version"),
                    "supported": MEMORY_FORMAT_VERSION,
                }
            )
        if not _uuid_valid(payload.get("snapshot_id")):
            errors.append({"code": "memory_snapshot_id_invalid", "actual": payload.get("snapshot_id")})
        created_at = payload.get("created_at_utc") or payload.get("generated_at_utc")
        if not _iso_datetime_valid(created_at):
            errors.append({"code": "memory_snapshot_timestamp_invalid", "actual": created_at})
        created_with_runtime = str(payload.get("created_with_runtime") or "").strip() or None
        if not created_with_runtime:
            errors.append({"code": "memory_created_with_runtime_missing"})
        compatibility = payload.get("compatibility")
        if not isinstance(compatibility, dict):
            errors.append({"code": "memory_compatibility_contract_missing"})
        else:
            compatibility_contract = str(compatibility.get("contract") or "").strip() or None
            if compatibility_contract != MEMORY_RUNTIME_COMPATIBILITY_CONTRACT:
                errors.append(
                    {
                        "code": "memory_compatibility_contract_unsupported",
                        "actual": compatibility_contract,
                        "supported": MEMORY_RUNTIME_COMPATIBILITY_CONTRACT,
                    }
                )
            if compatibility.get("runtime_version_is_provenance_only") is not True:
                errors.append({"code": "memory_runtime_version_policy_invalid"})
        if created_with_runtime and current_runtime:
            runtime_version_match = version_number(created_with_runtime) == version_number(current_runtime)
            if not runtime_version_match:
                warnings.append(
                    {
                        "code": "memory_created_with_different_runtime",
                        "created_with_runtime": created_with_runtime,
                        "current_runtime": current_runtime,
                        "policy": "provenance_only",
                    }
                )
        if payload.get("runtime_version"):
            warnings.append(
                {
                    "code": "memory_v2_deprecated_runtime_version_field",
                    "policy": "use created_with_runtime for provenance",
                }
            )

    expected_paths: set[str] = set()
    verified_count = 0
    sqlite_paths: set[str] = set()
    files = payload.get("files")
    if not isinstance(files, list):
        errors.append({"code": "memory_package_files_invalid"})
        files = []
    for item in files:
        if not isinstance(item, dict):
            errors.append({"code": "memory_package_file_entry_invalid"})
            continue
        relative = str(item.get("path") or "").replace("\\", "/").strip()
        parts = Path(relative).parts
        if (
            not relative
            or Path(relative).is_absolute()
            or ".." in parts
            or not relative.startswith("memory/")
        ):
            errors.append({"code": "memory_package_path_unsafe", "path": relative})
            continue
        lowered = relative.lower()
        if lowered.endswith(TRANSIENT_DATABASE_SUFFIXES):
            errors.append({"code": "memory_package_transient_database_file", "path": relative})
        if relative == MEMORY_PACKAGE_MANIFEST_PATH or relative in expected_paths:
            errors.append({"code": "memory_package_path_duplicate_or_self", "path": relative})
            continue
        expected_paths.add(relative)
        target = (package_root / Path(*relative.split("/"))).resolve()
        try:
            target.relative_to(package_root)
        except ValueError:
            errors.append({"code": "memory_package_path_escapes_root", "path": relative})
            continue
        if not target.is_file():
            errors.append({"code": "memory_package_file_missing", "path": relative})
            continue
        expected_size = int(item.get("size_bytes", -1))
        expected_sha = str(item.get("sha256") or "").strip().lower()
        actual_size = target.stat().st_size
        actual_sha = sha256_file(target)
        if actual_size != expected_size:
            errors.append(
                {
                    "code": "memory_package_file_size_mismatch",
                    "path": relative,
                    "expected": expected_size,
                    "actual": actual_size,
                }
            )
        if actual_sha != expected_sha:
            errors.append(
                {
                    "code": "memory_package_file_sha256_mismatch",
                    "path": relative,
                    "expected": expected_sha,
                    "actual": actual_sha,
                }
            )
        if actual_size == expected_size and actual_sha == expected_sha:
            verified_count += 1
        if _sqlite_file(target):
            sqlite_paths.add(relative)

    memory_root = package_root / "memory"
    actual_paths = (
        {
            path.relative_to(package_root).as_posix()
            for path in memory_root.rglob("*")
            if path.is_file() and path.resolve() != manifest_path.resolve()
        }
        if memory_root.is_dir()
        else set()
    )
    for extra in sorted(actual_paths - expected_paths):
        errors.append({"code": "memory_package_unlisted_file", "path": extra})
    declared_count = int(payload.get("file_count", -1))
    if declared_count != len(expected_paths):
        errors.append(
            {
                "code": "memory_package_file_count_mismatch",
                "declared": declared_count,
                "actual": len(expected_paths),
            }
        )

    database_reports: list[dict[str, Any]] = []
    declared_database_paths: set[str] = set()
    databases = payload.get("databases") if schema == MEMORY_MANIFEST_SCHEMA_V2 else []
    if schema == MEMORY_MANIFEST_SCHEMA_V2 and not isinstance(databases, list):
        errors.append({"code": "memory_database_manifest_invalid"})
        databases = []
    for item in databases or []:
        if not isinstance(item, dict):
            errors.append({"code": "memory_database_entry_invalid"})
            continue
        relative = str(item.get("path") or "").replace("\\", "/").strip()
        if relative in declared_database_paths:
            errors.append({"code": "memory_database_entry_duplicate", "path": relative})
            continue
        declared_database_paths.add(relative)
        if relative not in expected_paths:
            errors.append({"code": "memory_database_not_in_files", "path": relative})
            continue
        target = package_root / Path(*relative.split("/"))
        if not target.is_file() or not _sqlite_file(target):
            errors.append({"code": "memory_database_not_sqlite", "path": relative})
            continue
        try:
            report = inspect_sqlite_memory_file(target)
        except (sqlite3.Error, OSError) as exc:
            errors.append(
                {
                    "code": "memory_database_validation_error",
                    "path": relative,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
            continue
        report["relative_path"] = relative
        database_reports.append(report)
        if report.get("ok") is not True:
            errors.append(
                {
                    "code": "memory_database_integrity_failed",
                    "path": relative,
                    "integrity_check": report.get("integrity_check"),
                    "foreign_key_error_count": report.get("foreign_key_error_count"),
                }
            )
        for field in ("user_version", "application_id", "schema_sha256", "size_bytes", "sha256"):
            if item.get(field) is not None and item.get(field) != report.get(field):
                errors.append(
                    {
                        "code": "memory_database_metadata_mismatch",
                        "path": relative,
                        "field": field,
                        "declared": item.get(field),
                        "actual": report.get(field),
                    }
                )
        if item.get("snapshot_method") != "sqlite_online_backup_api":
            errors.append(
                {
                    "code": "memory_database_snapshot_method_unsupported",
                    "path": relative,
                    "actual": item.get("snapshot_method"),
                }
            )

    if schema == MEMORY_MANIFEST_SCHEMA_V2:
        for missing in sorted(sqlite_paths - declared_database_paths):
            errors.append({"code": "memory_database_metadata_missing", "path": missing})
        for extra in sorted(declared_database_paths - sqlite_paths):
            errors.append({"code": "memory_database_metadata_extra", "path": extra})
    else:
        if sqlite_paths:
            warnings.append({
                "code": "legacy_memory_sqlite_snapshot_consistency_unverifiable",
                "policy": "structural_integrity_verified_but_original_wal_completeness_unknown",
            })
        for relative in sorted(sqlite_paths):
            target = package_root / Path(*relative.split("/"))
            try:
                report = inspect_sqlite_memory_file(target)
                report["relative_path"] = relative
                database_reports.append(report)
                if report.get("ok") is not True:
                    errors.append({"code": "memory_database_integrity_failed", "path": relative})
            except (sqlite3.Error, OSError) as exc:
                errors.append(
                    {
                        "code": "memory_database_validation_error",
                        "path": relative,
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )

    compatibility_ok = bool(
        schema == MEMORY_MANIFEST_SCHEMA_V1
        or (
            schema == MEMORY_MANIFEST_SCHEMA_V2
            and compatibility_contract == MEMORY_RUNTIME_COMPATIBILITY_CONTRACT
        )
    )
    return {
        "ok": not errors,
        "status": "verified" if not errors else "invalid",
        "manifest_path": str(manifest_path),
        "manifest_schema": schema,
        "memory_format_version": payload.get("memory_format_version") if schema == MEMORY_MANIFEST_SCHEMA_V2 else 1,
        "snapshot_id": payload.get("snapshot_id"),
        "created_with_runtime": created_with_runtime,
        "current_runtime": current_runtime,
        "runtime_version_match": runtime_version_match,
        "runtime_version_is_provenance_only": True,
        "compatibility_contract": compatibility_contract,
        "compatibility_ok": compatibility_ok,
        "declared_file_count": declared_count,
        "verified_file_count": verified_count,
        "sqlite_database_count": len(sqlite_paths),
        "database_reports": database_reports,
        "errors": errors,
        "warnings": warnings,
        "truth_boundary": TRUTH_BOUNDARY,
    }


def _safe_remove_tree(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)


def _package_tree_is_memory_only(root: Path) -> tuple[bool, list[str]]:
    extras: list[str] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        if not relative.startswith("memory/"):
            extras.append(relative)
    return not extras, extras


def _attach_memory_package_impl(
    runtime_root: Path,
    *,
    parts_dir: Path,
    base_zip_name: str | None = None,
    work_dir: Path | None = None,
    time_budget_seconds: float | None = 25.0,
    run_crc: bool = True,
    force_reextract: bool = False,
) -> MemoryAttachResult:
    runtime_root = Path(runtime_root).expanduser().resolve()
    parts_dir = Path(parts_dir).expanduser().resolve()
    default_work = runtime_root / "workspace_runtime" / "memory_attach" / "package_work"
    work_dir = Path(work_dir).expanduser().resolve() if work_dir is not None else default_work
    report: dict[str, Any] = {
        "runtime_root": str(runtime_root),
        "parts_dir": str(parts_dir),
        "work_dir": str(work_dir),
        "started_at_epoch": time.time(),
    }

    installation = _runtime_installation_status(runtime_root)
    report["runtime_installation"] = installation
    if installation.get("ok") is not True:
        return MemoryAttachResult(
            ok=False,
            state="runtime_not_verified",
            runtime_root=str(runtime_root),
            report=report,
            exit_code=13,
        )

    config = JaznConfig(root=runtime_root)
    daemon = status_daemon(config)
    report["daemon_status_before"] = daemon
    if daemon.get("active_state") in {"active_trusted", "active_degraded"}:
        report["blocking_reason"] = "runtime_daemon_must_be_stopped_before_memory_attach"
        report["recovery_hint"] = (
            "Uruchom runtime-bootstrap z --no-start-daemon albo zatrzymaj daemon, dołącz pamięć i dopiero potem uruchom runtime."
        )
        return MemoryAttachResult(
            ok=False,
            state="runtime_active_attach_blocked",
            runtime_root=str(runtime_root),
            report=report,
            exit_code=12,
        )

    work_dir.mkdir(parents=True, exist_ok=True)
    zip_name = infer_base_zip_name(parts_dir, base_zip_name)
    report["base_zip_name"] = zip_name
    package_set = load_package_set_metadata(parts_dir, zip_name)
    report["package_set"] = package_set
    if package_set.get("source") != "package.json" or package_set.get("profile") != "memory":
        report["profile_gate"] = {
            "ok": False,
            "reason": "memory_attach_requires_explicit_memory_profile",
            "declared_profile": package_set.get("profile"),
            "contract_source": package_set.get("source"),
        }
        return MemoryAttachResult(
            ok=False,
            state="memory_package_profile_rejected",
            runtime_root=str(runtime_root),
            report=report,
            exit_code=14,
        )

    expected, expected_full_sha, expectation_source = load_package_expectations(parts_dir, zip_name)
    report["expectations_source"] = expectation_source
    report["expected_parts_count"] = len(expected)
    report["expected_full_sha256"] = expected_full_sha
    canonical_dir = work_dir / "canonical_parts"
    if force_reextract and canonical_dir.exists():
        _safe_remove_tree(canonical_dir)
    resolved = resolve_renamed_package_parts(
        parts_dir,
        expected,
        canonical_dir=canonical_dir,
        skip_part_hash=False,
    )
    report["part_resolution"] = resolved

    archive_format = str(package_set.get("archive_format") or "").strip().lower()
    independent_paths: list[Path] = []
    joined_zip: Path | None = None
    if archive_format == "independent":
        independent_paths = [canonical_dir / part.filename for part in expected]
        zip_report = {
            "ok": True,
            "archive_format": "independent",
            "volumes": [test_joined_zip(path, run_crc=run_crc) for path in independent_paths],
        }
    elif archive_format == "binary":
        joined_zip = join_split_package_to_zip(
            canonical_dir,
            zip_name,
            zip_out=work_dir / zip_name,
            force=True,
            keep_existing=False,
        )
        zip_report = test_joined_zip(joined_zip, run_crc=run_crc)
    else:
        raise ValueError(f"unsupported archive_format: {archive_format!r}")
    report["zip_test"] = zip_report

    staging = work_dir / "staging"
    if force_reextract and staging.exists():
        _safe_remove_tree(staging)
    if archive_format == "independent":
        extraction = extract_independent_zip_set_resumable(
            independent_paths,
            staging,
            progress_path=work_dir / "extract-progress.json",
            time_budget_seconds=time_budget_seconds,
        )
    else:
        assert joined_zip is not None
        extraction = extract_joined_zip_resumable(
            joined_zip,
            staging,
            progress_path=work_dir / "extract-progress.json",
            time_budget_seconds=time_budget_seconds,
        )
    report["extraction"] = extraction
    if extraction.get("pending"):
        return MemoryAttachResult(
            ok=False,
            pending=True,
            state="memory_extracting_pending",
            runtime_root=str(runtime_root),
            report=report,
            exit_code=75,
        )

    if archive_format == "independent":
        tree_verification = verify_extracted_zip_set(
            independent_paths,
            staging,
            reject_extra_files=True,
        )
    else:
        assert joined_zip is not None
        tree_verification = verify_extracted_zip_tree(
            joined_zip,
            staging,
            reject_extra_files=True,
        )
    report["filesystem_verification"] = tree_verification
    if tree_verification.get("ok") is not True:
        return MemoryAttachResult(
            ok=False,
            state="memory_archive_verification_failed",
            runtime_root=str(runtime_root),
            report=report,
            exit_code=15,
        )

    memory_only, extras = _package_tree_is_memory_only(staging)
    report["memory_only_tree"] = {"ok": memory_only, "extra_paths": extras}
    if not memory_only:
        return MemoryAttachResult(
            ok=False,
            state="memory_package_contains_non_memory_files",
            runtime_root=str(runtime_root),
            report=report,
            exit_code=14,
        )

    verification = verify_memory_package_manifest(staging, runtime_root=runtime_root)
    report["memory_manifest_verification"] = verification
    if verification.get("ok") is not True:
        return MemoryAttachResult(
            ok=False,
            state="memory_manifest_verification_failed",
            runtime_root=str(runtime_root),
            report=report,
            exit_code=15,
        )

    source_memory = staging / "memory"
    if not source_memory.is_dir():
        report["blocking_reason"] = "memory_directory_missing_after_extract"
        return MemoryAttachResult(
            ok=False,
            state="memory_payload_missing",
            runtime_root=str(runtime_root),
            report=report,
            exit_code=15,
        )

    transaction_id = str(uuid.uuid4())
    transaction_root = runtime_root / "workspace_runtime" / "memory_attach" / transaction_id
    candidate_root = transaction_root / "candidate_root"
    candidate_memory = candidate_root / "memory"
    previous_memory = transaction_root / "previous_memory"
    transaction_root.mkdir(parents=True, exist_ok=False)
    candidate_root.mkdir(parents=True, exist_ok=True)
    try:
        os.replace(source_memory, candidate_memory)
        report["candidate_materialization"] = "atomic_move_from_staging"
    except OSError as exc:
        if exc.errno != errno.EXDEV:
            raise
        shutil.copytree(source_memory, candidate_memory)
        report["candidate_materialization"] = "cross_filesystem_copy"
    candidate_verification = verify_memory_package_manifest(candidate_root, runtime_root=runtime_root)
    report["candidate_verification"] = candidate_verification
    if candidate_verification.get("ok") is not True:
        _safe_remove_tree(transaction_root)
        return MemoryAttachResult(
            ok=False,
            state="memory_candidate_verification_failed",
            runtime_root=str(runtime_root),
            report=report,
            exit_code=15,
        )

    target_memory = runtime_root / "memory"
    moved_previous = False
    installed_new = False
    try:
        if target_memory.exists():
            os.replace(target_memory, previous_memory)
            moved_previous = True
        os.replace(candidate_memory, target_memory)
        installed_new = True
        post = verify_memory_package_manifest(runtime_root, runtime_root=runtime_root)
        report["post_install_verification"] = post
        if post.get("ok") is not True:
            raise RuntimeError("post-install memory verification failed")
    except Exception as exc:
        report["transaction_error"] = f"{type(exc).__name__}: {exc}"
        try:
            if installed_new and target_memory.exists():
                failed_memory = transaction_root / "failed_new_memory"
                os.replace(target_memory, failed_memory)
            if moved_previous and previous_memory.exists():
                os.replace(previous_memory, target_memory)
            report["rollback_ok"] = bool(not moved_previous or target_memory.exists())
        except Exception as rollback_exc:
            report["rollback_ok"] = False
            report["rollback_error"] = f"{type(rollback_exc).__name__}: {rollback_exc}"
        return MemoryAttachResult(
            ok=False,
            state="memory_attach_transaction_failed",
            runtime_root=str(runtime_root),
            report=report,
            exit_code=16,
        )

    manifest_path = runtime_root / MEMORY_PACKAGE_MANIFEST_PATH
    marker = {
        "schema_version": ATTACH_SCHEMA_VERSION,
        "attached_at_utc": datetime.now(timezone.utc).isoformat(),
        "runtime_root": str(runtime_root),
        "runtime_version": installation.get("version"),
        "memory_manifest_path": str(manifest_path),
        "memory_manifest_sha256": sha256_file(manifest_path),
        "memory_manifest_schema": verification.get("manifest_schema"),
        "memory_format_version": verification.get("memory_format_version"),
        "memory_snapshot_id": verification.get("snapshot_id"),
        "created_with_runtime": verification.get("created_with_runtime"),
        "compatibility_contract": verification.get("compatibility_contract"),
        "runtime_version_is_provenance_only": True,
        "package_name": zip_name,
        "truth_boundary": TRUTH_BOUNDARY,
    }
    marker_path = runtime_root / ATTACH_MARKER_PATH
    _write_json_atomic(marker_path, marker)
    report["attach_marker"] = marker
    report["attach_marker_path"] = str(marker_path)
    if previous_memory.exists():
        _safe_remove_tree(previous_memory)
    _safe_remove_tree(transaction_root)
    report["transaction_committed"] = True
    report["daemon_status_after"] = status_daemon(config)
    return MemoryAttachResult(
        ok=True,
        state="memory_attached_inactive",
        runtime_root=str(runtime_root),
        report=report,
        exit_code=0,
    )


def attach_memory_package(
    runtime_root: Path,
    *,
    parts_dir: Path,
    base_zip_name: str | None = None,
    work_dir: Path | None = None,
    time_budget_seconds: float | None = 25.0,
    run_crc: bool = True,
    force_reextract: bool = False,
) -> MemoryAttachResult:
    """Fail-closed host boundary for attaching a verified memory-only package."""

    try:
        return _attach_memory_package_impl(
            runtime_root,
            parts_dir=parts_dir,
            base_zip_name=base_zip_name,
            work_dir=work_dir,
            time_budget_seconds=time_budget_seconds,
            run_crc=run_crc,
            force_reextract=force_reextract,
        )
    except PermissionError as exc:
        code = "memory_attach_path_unwritable"
        hint = "Sprawdź uprawnienia runtime_root/workspace_runtime i wolne miejsce."
        error_type, error_detail = type(exc).__name__, str(exc)
    except FileNotFoundError as exc:
        code = "memory_package_source_missing"
        hint = "Sprawdź parts-dir, sidecar package.json oraz komplet części paczki memory."
        error_type, error_detail = type(exc).__name__, str(exc)
    except ValueError as exc:
        code = "memory_package_contract_invalid"
        hint = "Użyj paczki memory wygenerowanej przez bieżący generator i nie omijaj sidecara."
        error_type, error_detail = type(exc).__name__, str(exc)
    except sqlite3.Error as exc:
        code = "memory_package_sqlite_validation_failed"
        hint = "Nie dołączono pamięci; sprawdź integralność i schemat baz SQLite w paczce."
        error_type, error_detail = type(exc).__name__, str(exc)
    except OSError as exc:
        code = "memory_attach_io_error"
        hint = "Sprawdź filesystem, wolne miejsce i dostępność katalogów staging/transaction."
        error_type, error_detail = type(exc).__name__, str(exc)
    except Exception as exc:
        code = "memory_attach_failed"
        hint = "Zachowaj raport; pamięć nie została uznana za dołączoną."
        error_type, error_detail = type(exc).__name__, str(exc)
    try:
        resolved_root = str(Path(runtime_root).expanduser().resolve())
    except (OSError, RuntimeError):
        resolved_root = str(runtime_root)
    return MemoryAttachResult(
        ok=False,
        state="memory_attach_blocked",
        runtime_root=resolved_root,
        report={
            "runtime_root": str(runtime_root),
            "parts_dir": str(parts_dir),
            "work_dir": str(work_dir) if work_dir is not None else None,
            "error": {"code": code, "type": error_type, "detail": error_detail},
            "recovery_hint": hint,
            "truth_boundary": TRUTH_BOUNDARY,
        },
        exit_code=17,
    )


__all__ = [
    "ATTACH_MARKER_PATH",
    "MEMORY_FORMAT_VERSION",
    "MEMORY_MANIFEST_SCHEMA_V1",
    "MEMORY_MANIFEST_SCHEMA_V2",
    "MEMORY_PACKAGE_MANIFEST_PATH",
    "MEMORY_RUNTIME_COMPATIBILITY_CONTRACT",
    "MemoryAttachResult",
    "attach_memory_package",
    "inspect_sqlite_memory_file",
    "verify_memory_package_manifest",
]
