from __future__ import annotations

from contextlib import closing
from pathlib import Path
from typing import Any, Callable, Mapping
import sqlite3

from latka_jazn.db.runtime_sqlite import connect_runtime_readonly
from latka_jazn.tools.memory_rebuild_app.unified_schema import (
    COMPATIBLE_UNIFIED_SCHEMA_VERSIONS,
)
from latka_jazn.version import schema_version


SCHEMA_VERSION = schema_version("unified_memory_runtime_probe")
_REQUIRED_NATIVE_TABLES = {
    "unified_memory_meta",
    "import_sources",
    "conversations",
    "nodes",
    "fts_docs",
    "journal_entries",
    "journal_fts_docs",
    "candidates",
    "experiences",
    "experience_fts_docs",
    "memory_records",
    "memory_evidence",
    "sources",
}
_BASE_FTS = {
    "message_fts": "fts_docs",
    "journal_fts": "journal_fts_docs",
    "experience_fts": "experience_fts_docs",
}


def _cancelled(should_continue: Callable[[], bool] | None) -> bool:
    if should_continue is None:
        return False
    try:
        return not bool(should_continue())
    except Exception:
        return True


def _progress_handler(should_continue: Callable[[], bool] | None) -> Callable[[], int] | None:
    if should_continue is None:
        return None

    def progress() -> int:
        return 1 if _cancelled(should_continue) else 0

    return progress


def probe_unified_memory_database(
    path: str | Path,
    *,
    busy_timeout_ms: int = 10_000,
    should_continue: Callable[[], bool] | None = None,
    full_integrity: bool = False,
) -> dict[str, Any]:
    database = Path(path).expanduser().resolve()
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "database": str(database),
        "exists": database.is_file(),
        "native_unified": False,
        "memory_search_ready": False,
        "read_only": True,
        "issues": [],
    }
    if not database.is_file():
        report["status"] = "database_missing"
        return report
    try:
        with closing(connect_runtime_readonly(database, timeout_ms=busy_timeout_ms)) as con:
            progress = _progress_handler(should_continue)
            if progress is not None:
                con.set_progress_handler(progress, 2_000)
            pragma = "integrity_check" if full_integrity else "quick_check"
            integrity = [str(row[0]) for row in con.execute(f"PRAGMA {pragma}")]
            foreign_keys = [tuple(row) for row in con.execute("PRAGMA foreign_key_check")]
            objects = {
                str(row[0]): str(row[1] or "")
                for row in con.execute(
                    "SELECT name,sql FROM sqlite_master WHERE type IN ('table','view')"
                )
            }
            schema_identity = None
            if "unified_memory_meta" in objects:
                row = con.execute(
                    "SELECT value FROM unified_memory_meta WHERE key='schema_version'"
                ).fetchone()
                schema_identity = str(row[0]) if row else None
            native = schema_identity in COMPATIBLE_UNIFIED_SCHEMA_VERSIONS
            missing_tables = sorted(_REQUIRED_NATIVE_TABLES - set(objects)) if native else []
            required_fts = dict(_BASE_FTS)
            if schema_identity == "jazn_unified_memory/v2.5":
                required_fts["memory_records_fts"] = "memory_records"
            missing_fts = sorted(
                name for name, docs in required_fts.items()
                if name not in objects or docs not in objects
            ) if native else []
            fts_counts: dict[str, dict[str, int]] = {}
            fts_errors: list[str] = []
            if native and not missing_fts:
                for fts_name, docs_name in required_fts.items():
                    try:
                        con.execute(f'SELECT rowid FROM "{fts_name}" WHERE "{fts_name}" MATCH ? LIMIT 1', ("jazn_probe_token",)).fetchall()
                        fts_count = int(con.execute(f'SELECT COUNT(*) FROM "{fts_name}"').fetchone()[0])
                        docs_count = int(con.execute(f'SELECT COUNT(*) FROM "{docs_name}"').fetchone()[0])
                        fts_counts[fts_name] = {"index_rows": fts_count, "source_rows": docs_count}
                        if fts_count != docs_count:
                            fts_errors.append(f"{fts_name}:row_count_mismatch")
                    except sqlite3.Error as exc:
                        fts_errors.append(f"{fts_name}:{type(exc).__name__}:{exc}")
            recall_probe_ok = False
            if native and not missing_tables and not _cancelled(should_continue):
                try:
                    for table in ("memory_records", "experiences", "journal_entries", "nodes"):
                        con.execute(f'SELECT 1 FROM "{table}" LIMIT 1').fetchone()
                    recall_probe_ok = True
                except sqlite3.Error as exc:
                    report["issues"].append(f"recall_probe:{type(exc).__name__}:{exc}")
    except (OSError, sqlite3.Error) as exc:
        report.update({
            "status": "database_probe_failed",
            "error_type": type(exc).__name__,
            "error": str(exc),
        })
        return report

    report.update({
        "native_unified": native,
        "schema_identity": schema_identity,
        "supported_schema_identities": list(COMPATIBLE_UNIFIED_SCHEMA_VERSIONS),
        "integrity_check": integrity,
        "foreign_key_error_count": len(foreign_keys),
        "foreign_key_errors": foreign_keys[:32],
        "missing_required_tables": missing_tables,
        "missing_fts_objects": missing_fts,
        "fts_counts": fts_counts,
        "fts_errors": fts_errors,
        "recall_probe_ok": recall_probe_ok,
        "cancelled": _cancelled(should_continue),
    })
    ready = bool(
        native
        and integrity == ["ok"]
        and not foreign_keys
        and not missing_tables
        and not missing_fts
        and not fts_errors
        and recall_probe_ok
        and not report["cancelled"]
    )
    report["memory_search_ready"] = ready
    if ready:
        report["status"] = "ready_native_unified"
    elif not native:
        report["status"] = "not_native_unified"
    elif report["cancelled"]:
        report["status"] = "probe_cancelled"
    else:
        report["status"] = "native_unified_not_ready"
    return report


def probe_legacy_memory_layout(
    database_paths: Mapping[str, str | Path],
    *,
    busy_timeout_ms: int = 10_000,
    should_continue: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    required_table = {
        "memory_jazn": "memory_records",
        "experience": "experiences",
        "journal": "journal_entries",
        "archive_chats": "nodes",
    }
    readable: list[str] = []
    issues: list[str] = []
    for layer, table in required_table.items():
        if _cancelled(should_continue):
            break
        raw_path = database_paths.get(layer)
        if not raw_path:
            continue
        path = Path(raw_path).expanduser().resolve()
        if not path.is_file():
            continue
        try:
            with closing(connect_runtime_readonly(path, timeout_ms=busy_timeout_ms)) as con:
                progress = _progress_handler(should_continue)
                if progress is not None:
                    con.set_progress_handler(progress, 2_000)
                integrity = str(con.execute("PRAGMA quick_check").fetchone()[0])
                foreign_keys = list(con.execute("PRAGMA foreign_key_check"))
                exists = con.execute(
                    "SELECT 1 FROM sqlite_master WHERE type IN ('table','view') AND name=?",
                    (table,),
                ).fetchone()
                if integrity == "ok" and not foreign_keys and exists:
                    con.execute(f'SELECT 1 FROM "{table}" LIMIT 1').fetchone()
                    readable.append(layer)
                else:
                    issues.append(f"{layer}:integrity_or_schema_invalid")
        except (OSError, sqlite3.Error) as exc:
            issues.append(f"{layer}:{type(exc).__name__}:{exc}")
    return {
        "schema_version": schema_version("legacy_memory_runtime_probe"),
        "status": "legacy_compatibility_ready" if readable else "legacy_compatibility_not_ready",
        "legacy_compatibility_only": True,
        "readable_layers": readable,
        "legacy_search_ready": bool(readable) and not _cancelled(should_continue),
        "memory_search_ready": False,
        "cancelled": _cancelled(should_continue),
        "issues": issues,
        "read_only": True,
    }


__all__ = [
    "COMPATIBLE_UNIFIED_SCHEMA_VERSIONS",
    "probe_legacy_memory_layout",
    "probe_unified_memory_database",
]
