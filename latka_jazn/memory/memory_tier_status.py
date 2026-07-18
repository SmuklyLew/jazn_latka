from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
import sqlite3

from latka_jazn.memory.memory_tier_store import MemoryTierStore
from latka_jazn.version import schema_version

SCHEMA_VERSION = schema_version("memory_tier_status")


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
    error_type: str | None = None
    error: str | None = None
    schema_version: str = SCHEMA_VERSION
    truth_boundary: str = (
        "Status potwierdza stan bazy L1/L2/L3. Nie dowodzi poprawnego recall, "
        "aktywnej tożsamości ani wykonania zdarzeń outbox."
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def inspect_memory_tier_store(path: str | Path, *, full: bool = False) -> MemoryTierStatus:
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
    try:
        with MemoryTierStore(database) as store:
            result = store.validate(full=full)
        return MemoryTierStatus(
            path=str(database),
            exists=True,
            size_bytes=database.stat().st_size,
            ready=bool(result.get("ok")),
            integrity_check=str(result.get("integrity_check")),
            foreign_key_error_count=int(result.get("foreign_key_error_count") or 0),
            automatic_commit_violation_count=int(result.get("automatic_commit_violation_count") or 0),
            stats={str(key): int(value) for key, value in dict(result.get("stats") or {}).items()},
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
