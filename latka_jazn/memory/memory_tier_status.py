from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
import sqlite3

from latka_jazn.version import schema_version

SCHEMA_VERSION = schema_version("memory_tier_status")
REQUIRED_TABLES = (
    "memory_store_meta",
    "memory_records",
    "memory_evidence",
    "working_memory_index",
    "short_term_memory_index",
    "long_term_memory_index",
    "promotion_requests",
    "promotion_decisions",
    "promotion_ledger",
    "memory_outbox",
    "session_checkpoints",
)


@dataclass(slots=True, frozen=True)
class MemoryTierStatus:
    path: str
    exists: bool
    size_bytes: int
    ready: bool
    integrity_check: str | None
    foreign_key_error_count: int | None
    automatic_commit_violation_count: int | None
    stats: dict[str, int]
    store_schema_version: str | None = None
    missing_tables: tuple[str, ...] = ()
    error_type: str | None = None
    error: str | None = None
    read_only: bool = True
    schema_version: str = SCHEMA_VERSION
    truth_boundary: str = (
        "Status potwierdza stan bazy L1/L2/L3. Nie dowodzi poprawnego recall, "
        "aktywnej tożsamości ani wykonania zdarzeń outbox."
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def inspect_memory_tier_store(path: str | Path, *, full: bool = False) -> MemoryTierStatus:
    """Inspect the tier database without creating schema, WAL or metadata writes."""
    database = Path(path).expanduser().resolve()
    if not database.is_file():
        return MemoryTierStatus(
            path=str(database),
            exists=False,
            size_bytes=0,
            ready=False,
            integrity_check=None,
            foreign_key_error_count=None,
            automatic_commit_violation_count=None,
            stats={},
            error_type="FileNotFoundError",
            error="memory tier database is missing",
        )
    con: sqlite3.Connection | None = None
    try:
        uri = f"file:{database.as_posix()}?mode=ro"
        con = sqlite3.connect(uri, uri=True, timeout=10.0)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA query_only=ON")
        con.execute("PRAGMA busy_timeout=10000")
        present = {
            str(row[0])
            for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        missing = tuple(sorted(set(REQUIRED_TABLES) - present))
        pragma = "integrity_check" if full else "quick_check"
        integrity = str(con.execute(f"PRAGMA {pragma}").fetchone()[0])
        foreign_keys = list(con.execute("PRAGMA foreign_key_check"))
        stats = {
            table: int(con.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
            for table in REQUIRED_TABLES
            if table in present
        }
        automatic_commit = (
            int(con.execute(
                "SELECT COUNT(*) FROM promotion_decisions WHERE automatic_commit_allowed<>0"
            ).fetchone()[0])
            if "promotion_decisions" in present
            else None
        )
        schema_row = (
            con.execute(
                "SELECT value FROM memory_store_meta WHERE key='schema_version'"
            ).fetchone()
            if "memory_store_meta" in present
            else None
        )
        store_schema = str(schema_row[0]) if schema_row else None
        ready = integrity == "ok" and not foreign_keys and not missing and automatic_commit == 0
        return MemoryTierStatus(
            path=str(database),
            exists=True,
            size_bytes=database.stat().st_size,
            ready=ready,
            integrity_check=integrity,
            foreign_key_error_count=len(foreign_keys),
            automatic_commit_violation_count=automatic_commit,
            stats=stats,
            store_schema_version=store_schema,
            missing_tables=missing,
            error_type="SchemaError" if missing else None,
            error=(f"memory tier schema is missing: {', '.join(missing)}" if missing else None),
        )
    except (sqlite3.DatabaseError, OSError, ValueError) as exc:
        return MemoryTierStatus(
            path=str(database),
            exists=True,
            size_bytes=database.stat().st_size if database.exists() else 0,
            ready=False,
            integrity_check=None,
            foreign_key_error_count=None,
            automatic_commit_violation_count=None,
            stats={},
            error_type=type(exc).__name__,
            error=str(exc),
        )
    finally:
        if con is not None:
            con.close()
