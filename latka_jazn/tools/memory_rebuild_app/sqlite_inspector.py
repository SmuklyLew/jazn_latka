from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable
import hashlib
import sqlite3

from .sqlite_utils import ClosingSQLiteConnection

DATABASE_FILENAMES: dict[str, str] = {
    "archive_chats": "archive_chats.sqlite3",
    "journal": "journal.sqlite3",
    "experience": "experience.sqlite3",
    "memory_jazn": "memory_jazn.sqlite3",
    "import_catalog": "import_catalog.sqlite3",
}

KNOWN_COUNT_TABLES: dict[str, tuple[str, ...]] = {
    "archive_chats": (
        "conversations",
        "nodes",
        "messages",
        "message_content",
        "import_sources",
        "import_source_aliases",
    ),
    "journal": (
        "journal_sources",
        "journal_entries",
        "journal_entry_revisions",
    ),
    "experience": (
        "experience_candidates",
        "experiences",
        "experience_domains",
    ),
    "memory_jazn": (
        "memory_records",
        "memory_tier_records",
        "promotion_requests",
        "promotion_decisions",
    ),
    "import_catalog": (
        "sources",
        "operations",
        "validations",
        "relations",
    ),
}


def sha256_file(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_database_root(value: str | Path) -> Path:
    root = Path(value).expanduser().resolve()
    candidates = [root, root / "memory" / "sqlite", root / "sqlite"]
    for candidate in candidates:
        if any((candidate / filename).is_file() for filename in DATABASE_FILENAMES.values()):
            return candidate
    return root


def resolve_database_paths(value: str | Path) -> dict[str, Path]:
    root = resolve_database_root(value)
    return {name: root / filename for name, filename in DATABASE_FILENAMES.items()}


def _quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _readonly_connection(path: Path) -> sqlite3.Connection:
    uri = path.resolve().as_uri() + "?mode=ro"
    connection = sqlite3.connect(uri, uri=True, timeout=10.0, factory=ClosingSQLiteConnection)
    connection.row_factory = sqlite3.Row
    return connection


@dataclass(slots=True)
class DatabaseInspection:
    name: str
    path: str
    exists: bool
    size_bytes: int | None = None
    sha256: str | None = None
    integrity_result: list[str] = field(default_factory=list)
    foreign_key_violations: list[dict[str, Any]] = field(default_factory=list)
    tables: list[str] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)
    journal_mode: str | None = None
    user_version: int | None = None
    schema_version: int | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return (
            self.exists
            and self.error is None
            and self.integrity_result == ["ok"]
            and not self.foreign_key_violations
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "name": self.name,
            "path": self.path,
            "exists": self.exists,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
            "integrity_result": list(self.integrity_result),
            "foreign_key_violations": list(self.foreign_key_violations),
            "tables": list(self.tables),
            "counts": dict(self.counts),
            "journal_mode": self.journal_mode,
            "user_version": self.user_version,
            "schema_version": self.schema_version,
            "error": self.error,
        }


def inspect_database(
    name: str,
    path: str | Path,
    *,
    full_integrity: bool = False,
    calculate_sha256: bool = True,
) -> DatabaseInspection:
    database = Path(path).expanduser().resolve()
    result = DatabaseInspection(name=name, path=str(database), exists=database.is_file())
    if not database.is_file():
        result.error = "database_missing"
        return result
    result.size_bytes = database.stat().st_size
    if calculate_sha256:
        result.sha256 = sha256_file(database)
    try:
        with _readonly_connection(database) as connection:
            pragma = "integrity_check" if full_integrity else "quick_check"
            result.integrity_result = [str(row[0]) for row in connection.execute(f"PRAGMA {pragma}")]
            result.foreign_key_violations = [
                {
                    "table": row[0],
                    "rowid": row[1],
                    "parent": row[2],
                    "foreign_key_index": row[3],
                }
                for row in connection.execute("PRAGMA foreign_key_check")
            ]
            result.tables = [
                str(row[0])
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
                )
            ]
            for table in KNOWN_COUNT_TABLES.get(name, ()):
                if table not in result.tables:
                    continue
                row = connection.execute(f"SELECT COUNT(*) FROM {_quote_identifier(table)}").fetchone()
                result.counts[table] = int(row[0]) if row else 0
            result.journal_mode = str(connection.execute("PRAGMA journal_mode").fetchone()[0])
            result.user_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
            result.schema_version = int(connection.execute("PRAGMA schema_version").fetchone()[0])
    except (sqlite3.Error, OSError) as exc:
        result.error = f"{type(exc).__name__}: {exc}"
    return result


def inspect_database_set(
    root: str | Path,
    *,
    full_integrity: bool = False,
    calculate_sha256: bool = True,
) -> dict[str, Any]:
    database_root = resolve_database_root(root)
    paths = resolve_database_paths(database_root)
    inspections = {
        name: inspect_database(
            name,
            path,
            full_integrity=full_integrity,
            calculate_sha256=calculate_sha256,
        )
        for name, path in paths.items()
    }
    available = sum(1 for item in inspections.values() if item.exists)
    return {
        "ok": available == len(DATABASE_FILENAMES) and all(item.ok for item in inspections.values()),
        "root": str(database_root),
        "available_database_count": available,
        "expected_database_count": len(DATABASE_FILENAMES),
        "databases": {name: item.to_dict() for name, item in inspections.items()},
    }


def _flatten_counts(summary: dict[str, Any]) -> dict[str, int]:
    result: dict[str, int] = {}
    for database_name, database in summary.get("databases", {}).items():
        for table, count in database.get("counts", {}).items():
            result[f"{database_name}.{table}"] = int(count)
    return result


def compare_database_summaries(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
) -> dict[str, Any]:
    baseline_counts = _flatten_counts(baseline)
    candidate_counts = _flatten_counts(candidate)
    keys = sorted(set(baseline_counts) | set(candidate_counts))
    rows: list[dict[str, Any]] = []
    declines: list[dict[str, Any]] = []
    for key in keys:
        before = int(baseline_counts.get(key, 0))
        after = int(candidate_counts.get(key, 0))
        row = {"metric": key, "baseline": before, "candidate": after, "delta": after - before}
        rows.append(row)
        if after < before:
            declines.append(row)
    missing_databases = [
        name
        for name in DATABASE_FILENAMES
        if baseline.get("databases", {}).get(name, {}).get("exists")
        and not candidate.get("databases", {}).get(name, {}).get("exists")
    ]
    hash_equal = {
        name: (
            baseline.get("databases", {}).get(name, {}).get("sha256")
            == candidate.get("databases", {}).get(name, {}).get("sha256")
        )
        for name in DATABASE_FILENAMES
        if baseline.get("databases", {}).get(name, {}).get("sha256")
        and candidate.get("databases", {}).get(name, {}).get("sha256")
    }
    return {
        "ok": not missing_databases and not declines and bool(candidate.get("ok")),
        "baseline_root": baseline.get("root"),
        "candidate_root": candidate.get("root"),
        "rows": rows,
        "declines": declines,
        "missing_databases": missing_databases,
        "database_sha256_equal": hash_equal,
    }


def compare_many(
    baselines: Iterable[dict[str, Any]],
    candidate: dict[str, Any],
) -> list[dict[str, Any]]:
    return [compare_database_summaries(baseline, candidate) for baseline in baselines]


__all__ = [
    "DATABASE_FILENAMES",
    "DatabaseInspection",
    "compare_database_summaries",
    "compare_many",
    "inspect_database",
    "inspect_database_set",
    "resolve_database_paths",
    "resolve_database_root",
]
