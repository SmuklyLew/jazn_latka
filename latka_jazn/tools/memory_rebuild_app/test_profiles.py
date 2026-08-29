from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable
import hashlib
import json
import sqlite3

from .read_only_validation import (
    open_read_only,
    promotion_ledger_validation,
    validate_existing_database,
)
from .unified_memory import CANONICAL_DATABASE_NAME
from .unified_schema import quote

PROFILE_NAMES = ("test01", "test02", "test03", "test04", "final")
_COMPARE_TABLES = (
    "conversations", "nodes", "fts_docs", "journal_entries",
    "candidates", "experiences", "memory_records",
)
_REQUIRED_TEST04_FIELDS = (
    "structural_integrity", "source_completeness", "same_target_idempotence",
    "fresh_rebuild_reproducibility", "test03_reconciliation", "recall",
    "multi_turn_review",
)


def _check(name: str, passed: bool, *, actual: Any = None, expected: Any = None,
           blocking: bool = True, detail: str = "") -> dict[str, Any]:
    return {
        "name": name, "passed": bool(passed), "blocking": bool(blocking),
        "actual": actual, "expected": expected, "detail": detail,
    }


def _baseline_files(root: Path) -> list[Path]:
    if not root.exists():
        raise FileNotFoundError(root)
    if root.is_file():
        if root.suffix.casefold() not in {".sqlite", ".sqlite3", ".db"}:
            raise ValueError(f"baseline is not SQLite: {root}")
        return [root]
    names = {
        "archive_chats.sqlite3", "journal.sqlite3", "experience.sqlite3",
        "memory_jazn.sqlite3", "import_catalog.sqlite3",
    }
    files = [path.resolve() for path in root.rglob("*.sqlite3") if path.name in names]
    if not files:
        raise FileNotFoundError(f"baseline contains no recognized SQLite databases: {root}")
    return files


def _pk_columns(con: sqlite3.Connection, table: str) -> list[str]:
    rows = list(con.execute(f"PRAGMA table_info({quote(table)})"))
    return [str(row[1]) for row in sorted((row for row in rows if int(row[5]) > 0), key=lambda row: int(row[5]))]


def _stable_key_hashes(path: Path, table: str) -> set[str]:
    with open_read_only(path) as con:
        exists = con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
        if not exists:
            return set()
        pk = _pk_columns(con, table)
        columns = pk
        if not columns:
            info = list(con.execute(f"PRAGMA table_info({quote(table)})"))
            columns = [str(row[1]) for row in info]
        if not columns:
            return set()
        selected = ",".join(quote(item) for item in columns)
        result: set[str] = set()
        for row in con.execute(f"SELECT {selected} FROM {quote(table)}"):
            payload = json.dumps(list(row), ensure_ascii=False, separators=(",", ":"), default=str)
            result.add(hashlib.sha256(payload.encode("utf-8")).hexdigest())
        return result


def baseline_record_reconciliation(database: str | Path, roots: Iterable[str | Path]) -> dict[str, Any]:
    target = Path(database).expanduser().resolve()
    roots = list(roots)
    if not roots:
        return {"ok": False, "reason": "baseline_required", "tables": {}}
    baseline_sets = {table: set() for table in _COMPARE_TABLES}
    files: list[Path] = []
    try:
        for raw in roots:
            files.extend(_baseline_files(Path(raw).expanduser().resolve()))
        for source in files:
            for table in _COMPARE_TABLES:
                baseline_sets[table].update(_stable_key_hashes(source, table))
        tables: dict[str, Any] = {}
        ok = True
        for table in _COMPARE_TABLES:
            target_keys = _stable_key_hashes(target, table)
            baseline_keys = baseline_sets[table]
            missing = baseline_keys - target_keys
            tables[table] = {
                "baseline_record_count": len(baseline_keys),
                "target_record_count": len(target_keys),
                "missing_record_count": len(missing),
                "missing_record_key_sha256_samples": sorted(missing)[:25],
            }
            if missing:
                ok = False
        return {
            "ok": ok,
            "baseline_database_count": len(files),
            "tables": tables,
            "comparison": "stable_primary_key_presence",
            "private_paths_persisted": False,
        }
    except (OSError, sqlite3.DatabaseError, ValueError) as exc:
        return {
            "ok": False, "reason": "baseline_read_error",
            "error_type": type(exc).__name__, "error": str(exc), "tables": {},
        }


def _unresolved_conflicts(path: Path) -> dict[str, int]:
    with open_read_only(path) as con:
        tables = {str(row[0]) for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        chat_conflicts = 0
        preserved_chat_divergences = 0
        if "import_conflicts" in tables:
            columns = {str(row[1]) for row in con.execute("PRAGMA table_info(import_conflicts)")}
            if "resolution_status" in columns:
                chat_conflicts = int(con.execute(
                    "SELECT COUNT(*) FROM import_conflicts "
                    "WHERE COALESCE(resolution_status,'unresolved')='unresolved'"
                ).fetchone()[0])
                preserved_chat_divergences = int(con.execute(
                    "SELECT COUNT(*) FROM import_conflicts WHERE resolution_status='preserved_union'"
                ).fetchone()[0])
            else:
                chat_conflicts = int(con.execute("SELECT COUNT(*) FROM import_conflicts").fetchone()[0])
        result = {
            "chat_import_conflicts": chat_conflicts,
            "migration_conflicts": int(con.execute("SELECT COUNT(*) FROM unified_migration_conflicts WHERE status='unresolved'").fetchone()[0]) if "unified_migration_conflicts" in tables else 0,
            "runtime_sync_conflicts": int(con.execute("SELECT COUNT(*) FROM runtime_memory_import_conflicts WHERE status='unresolved'").fetchone()[0]) if "runtime_memory_import_conflicts" in tables else 0,
        }
        result["total"] = sum(result.values())
        result["preserved_chat_divergences"] = preserved_chat_divergences
        return result


def _load_acceptance_report(path: str | Path | None) -> dict[str, Any]:
    if path is None:
        return {"ok": False, "reason": "full_test04_acceptance_report_required"}
    report_path = Path(path).expanduser().resolve()
    if not report_path.is_file():
        return {"ok": False, "reason": "acceptance_report_missing"}
    try:
        payload = json.loads(report_path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return {"ok": False, "reason": "acceptance_report_invalid", "error": str(exc)}
    final = payload.get("final") if isinstance(payload, dict) else None
    if not isinstance(final, dict):
        return {"ok": False, "reason": "acceptance_report_has_no_final_block"}
    required = {field: final.get(field) for field in _REQUIRED_TEST04_FIELDS}
    html = final.get("html_import_dry_run", "not_applicable")
    restart = final.get("restart_continuity", "not_run")
    required_ok = all(value == "passed" for value in required.values())
    html_ok = html in {"passed", "not_applicable"}
    return {
        "ok": required_ok and html_ok,
        "required": required,
        "html_import_dry_run": html,
        "restart_continuity": restart,
        "system_acceptance_restart_passed": restart == "passed",
        "source": "memory_sqlite_test04",
    }


def run_test_profile(
    database: str | Path,
    profile: str,
    *,
    baselines: Iterable[str | Path] = (),
    full_validation: bool = True,
    acceptance_report: str | Path | None = None,
    system_acceptance: bool = False,
) -> dict[str, Any]:
    selected = profile.strip().lower()
    if selected not in PROFILE_NAMES:
        raise ValueError(f"Nieznany profil {profile!r}. Dozwolone: {', '.join(PROFILE_NAMES)}")
    path = Path(database).expanduser().resolve()
    before = path.stat().st_mtime_ns if path.is_file() else None
    validation = validate_existing_database(path, full=full_validation, include_fts=True)
    stats = validation.get("stats") or {}
    fts = validation.get("fts") or {}
    checks: list[dict[str, Any]] = [
        _check("database_exists_and_read_only_validation", validation.get("reason") != "database_missing", actual=validation.get("reason"), expected="existing database"),
        _check("sqlite_integrity_and_foreign_keys", bool(validation.get("ok")), actual={
            "integrity": validation.get("integrity"), "foreign_key_error_count": validation.get("foreign_key_error_count")
        }),
        _check("single_physical_database", validation.get("single_physical_database") is True, actual=validation.get("legacy_sibling_databases"), expected=[]),
        _check("fts_integrity_and_smoke", bool(fts.get("ok")), actual=fts, expected="all present FTS indexes integrity-check + smoke query pass"),
        _check("conversations_present", int(stats.get("conversations", 0)) > 0, actual=stats.get("conversations", 0), expected=">0"),
        _check("nodes_present", int(stats.get("nodes", 0)) > 0, actual=stats.get("nodes", 0), expected=">0"),
        _check("conversation_search_index_present", int(stats.get("fts_docs", 0)) > 0, actual=stats.get("fts_docs", 0), expected=">0"),
    ]
    if selected in {"test02", "test03", "test04", "final"}:
        checks.append(_check("journal_present", int(stats.get("journal_entries", 0)) > 0, actual=stats.get("journal_entries", 0), expected=">0"))
    conflicts = _unresolved_conflicts(path) if path.is_file() else {"total": 1}
    if selected in {"test03", "test04", "final"}:
        checks.extend((
            _check("import_provenance_present", int(stats.get("import_sources", 0)) > 0, actual=stats.get("import_sources", 0), expected=">0"),
            _check("no_unresolved_import_or_migration_conflicts", conflicts.get("total", 0) == 0, actual=conflicts, expected={"total": 0}),
        ))
    reconciliation = {"ok": True, "status": "not_required"}
    acceptance = {"ok": True, "status": "not_required"}
    if selected in {"test04", "final"}:
        reconciliation = baseline_record_reconciliation(path, baselines)
        checks.append(_check(
            "test03_record_level_reconciliation", bool(reconciliation.get("ok")),
            actual=reconciliation, expected="baseline required and no missing stable record keys",
        ))
        acceptance = _load_acceptance_report(acceptance_report)
        acceptance_ok = bool(acceptance.get("ok"))
        if system_acceptance:
            acceptance_ok = acceptance_ok and bool(acceptance.get("system_acceptance_restart_passed"))
        checks.append(_check(
            "full_test04_acceptance", acceptance_ok, actual=acceptance,
            expected=(
                "passed: source completeness, idempotence, fresh rebuild, Test03 reconciliation, recall, "
                "multi-turn, HTML dry-run when applicable; restart/wake-state additionally for system acceptance"
            ),
            detail="system_acceptance=true requires restart_continuity=passed" if system_acceptance else "developer acceptance",
        ))
    ledger = {"ok": True, "status": "not_required"}
    if selected == "final" and path.is_file():
        ledger = promotion_ledger_validation(path)
        checks.append(_check(
            "l2_l3_verified_from_promotion_ledger", bool(ledger.get("ok")), actual=ledger,
            expected="no automatic commit decisions and every active L3 record backed by promotion decision+ledger",
        ))
        with open_read_only(path) as con:
            tables = {str(row[0]) for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            invalid_candidates = int(con.execute(
                "SELECT COUNT(*) FROM candidates WHERE confidence<0 OR confidence>1 OR importance<0 OR importance>1"
            ).fetchone()[0]) if "candidates" in tables else 0
            orphan_experiences = int(con.execute(
                "SELECT COUNT(*) FROM experiences e LEFT JOIN candidates c ON c.candidate_id=e.candidate_id WHERE c.candidate_id IS NULL"
            ).fetchone()[0]) if {"experiences", "candidates"}.issubset(tables) else 0
        checks.extend((
            _check("candidate_scores_valid", invalid_candidates == 0, actual=invalid_candidates, expected=0),
            _check("approved_experiences_have_candidates", orphan_experiences == 0, actual=orphan_experiences, expected=0),
        ))
    after = path.stat().st_mtime_ns if path.is_file() else None
    checks.append(_check(
        "validation_did_not_modify_database", before == after,
        actual={"before_mtime_ns": before, "after_mtime_ns": after}, expected="unchanged",
    ))
    blocking_failures = [item for item in checks if item["blocking"] and not item["passed"]]
    warnings = [item for item in checks if not item["blocking"] and not item["passed"]]
    return {
        "ok": not blocking_failures,
        "profile": selected,
        "database": str(path),
        "canonical_database_name": CANONICAL_DATABASE_NAME,
        "validation": validation,
        "stats": stats,
        "conflicts": conflicts,
        "baseline_reconciliation": reconciliation,
        "test04_acceptance": acceptance,
        "promotion_ledger_validation": ledger,
        "checks": checks,
        "blocking_failures": blocking_failures,
        "warnings": warnings,
        "read_only": True,
        "system_acceptance": bool(system_acceptance),
        "target_modified": False,
        "automatic_l2": ledger.get("automatic_l2", False) if selected == "final" else False,
        "automatic_l3": ledger.get("automatic_l3", False) if selected == "final" else False,
    }


# Kept for API compatibility; now returns strict aggregate counts and raises on unreadable baselines.
def baseline_counts(roots: Iterable[str | Path]) -> dict[str, int]:
    result = {table: 0 for table in _COMPARE_TABLES}
    for raw in roots:
        for database in _baseline_files(Path(raw).expanduser().resolve()):
            with open_read_only(database) as con:
                tables = {str(row[0]) for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                for table in _COMPARE_TABLES:
                    if table in tables:
                        result[table] += int(con.execute(f"SELECT COUNT(*) FROM {quote(table)}").fetchone()[0])
    return result


__all__ = ["PROFILE_NAMES", "baseline_counts", "baseline_record_reconciliation", "run_test_profile"]
