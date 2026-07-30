from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable
import sqlite3

from .unified_memory import CANONICAL_DATABASE_NAME, UnifiedMemoryDatabase

PROFILE_NAMES = ("test01", "test02", "test03", "test04", "final")
_COMPARE_TABLES = (
    "conversations", "nodes", "fts_docs", "journal_entries",
    "candidates", "experiences", "memory_records",
)


def _table_count(path: Path, table: str) -> int:
    uri = f"file:{path.as_posix()}?mode=ro"
    try:
        with sqlite3.connect(uri, uri=True, timeout=10) as con:
            exists = con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
            return int(con.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]) if exists else 0
    except sqlite3.DatabaseError:
        return 0


def _baseline_files(root: Path) -> list[Path]:
    if root.is_file() and root.suffix.lower() in {".sqlite", ".sqlite3", ".db"}:
        return [root]
    names = {
        "archive_chats.sqlite3", "journal.sqlite3", "experience.sqlite3",
        "memory_jazn.sqlite3", "import_catalog.sqlite3",
    }
    return [path for path in root.rglob("*.sqlite3") if path.name in names]


def baseline_counts(roots: Iterable[str | Path]) -> dict[str, int]:
    result = {table: 0 for table in _COMPARE_TABLES}
    for raw in roots:
        root = Path(raw).expanduser().resolve()
        per_root = {table: 0 for table in _COMPARE_TABLES}
        for database in _baseline_files(root):
            for table in _COMPARE_TABLES:
                per_root[table] = max(per_root[table], _table_count(database, table))
        for table in _COMPARE_TABLES:
            result[table] = max(result[table], per_root[table])
    return result


def _check(name: str, passed: bool, *, actual: Any = None, expected: Any = None, blocking: bool = True, detail: str = "") -> dict[str, Any]:
    return {
        "name": name,
        "passed": bool(passed),
        "blocking": bool(blocking),
        "actual": actual,
        "expected": expected,
        "detail": detail,
    }


def run_test_profile(
    database: str | Path,
    profile: str,
    *,
    baselines: Iterable[str | Path] = (),
    full_validation: bool = True,
) -> dict[str, Any]:
    selected = profile.strip().lower()
    if selected not in PROFILE_NAMES:
        raise ValueError(f"Nieznany profil {profile!r}. Dozwolone: {', '.join(PROFILE_NAMES)}")
    store = UnifiedMemoryDatabase(database)
    validation = store.validate(full=full_validation)
    stats = validation["stats"]
    checks: list[dict[str, Any]] = [
        _check("sqlite_integrity_and_foreign_keys", validation["ok"], actual=validation),
        _check("single_physical_database", validation.get("single_physical_database") is True, actual=validation.get("single_physical_database"), expected=True),
        _check("conversations_present", stats.get("conversations", 0) > 0, actual=stats.get("conversations", 0), expected=">0"),
        _check("nodes_present", stats.get("nodes", 0) > 0, actual=stats.get("nodes", 0), expected=">0"),
        _check("conversation_search_index_present", stats.get("fts_docs", 0) > 0, actual=stats.get("fts_docs", 0), expected=">0"),
    ]
    if selected in {"test02", "test03", "test04", "final"}:
        checks.append(_check("journal_present", stats.get("journal_entries", 0) > 0, actual=stats.get("journal_entries", 0), expected=">0"))
    if selected in {"test03", "test04", "final"}:
        checks.extend((
            _check("import_provenance_present", stats.get("import_sources", 0) > 0, actual=stats.get("import_sources", 0), expected=">0"),
            _check("no_unresolved_import_conflicts", stats.get("import_conflicts", 0) == 0, actual=stats.get("import_conflicts", 0), expected=0),
        ))
    baseline = baseline_counts(baselines)
    declines: dict[str, dict[str, int]] = {}
    if selected in {"test04", "final"} and any(baseline.values()):
        for table, expected in baseline.items():
            actual = int(stats.get(table, 0))
            if actual < expected:
                declines[table] = {"actual": actual, "baseline": expected}
            checks.append(_check(
                f"baseline_not_decreased:{table}", actual >= expected,
                actual=actual, expected=f">={expected}", blocking=expected > 0,
            ))
    if selected == "final":
        with store.connect(read_only=True) as con:
            invalid_candidates = int(con.execute(
                "SELECT COUNT(*) FROM candidates WHERE confidence<0 OR confidence>1 OR importance<0 OR importance>1"
            ).fetchone()[0])
            orphan_experiences = int(con.execute(
                "SELECT COUNT(*) FROM experiences e LEFT JOIN candidates c ON c.candidate_id=e.candidate_id WHERE c.candidate_id IS NULL"
            ).fetchone()[0])
            pending = int(con.execute("SELECT COUNT(*) FROM candidates WHERE status='pending_review'").fetchone()[0])
        checks.extend((
            _check("candidate_scores_valid", invalid_candidates == 0, actual=invalid_candidates, expected=0),
            _check("approved_experiences_have_candidates", orphan_experiences == 0, actual=orphan_experiences, expected=0),
            _check(
                "pending_candidates_reviewed_before_promotion", pending == 0,
                actual=pending, expected=0, blocking=False,
                detail="Kandydaci pending_review mogą pozostać w bazie, ale nie są doświadczeniami ani L2/L3.",
            ),
        ))
    blocking_failures = [item for item in checks if item["blocking"] and not item["passed"]]
    warnings = [item for item in checks if not item["blocking"] and not item["passed"]]
    return {
        "ok": not blocking_failures,
        "profile": selected,
        "database": str(store.path),
        "canonical_database_name": CANONICAL_DATABASE_NAME,
        "validation": validation,
        "stats": stats,
        "baseline_counts": baseline,
        "baseline_declines": declines,
        "checks": checks,
        "blocking_failures": blocking_failures,
        "warnings": warnings,
        "automatic_l2": False,
        "automatic_l3": False,
    }


__all__ = ["PROFILE_NAMES", "baseline_counts", "run_test_profile"]
