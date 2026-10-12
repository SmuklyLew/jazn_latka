from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import sqlite3
import uuid
from pathlib import Path
from typing import Any

from latka_jazn.version import PACKAGE_VERSION_FULL, schema_version

SCHEMA_VERSION = schema_version("database_identity")
TABLE_NAME = "jazn_database_identity"


@dataclass(slots=True)
class DatabaseIdentity:
    database_uuid: str
    schema_identity: str
    schema_version_number: int
    created_by_runtime: str
    created_at_utc: str
    trust_state: str = "trusted"
    schema_version: str = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def ensure_identity_table(connection: sqlite3.Connection) -> None:
    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {TABLE_NAME}(
          singleton INTEGER PRIMARY KEY CHECK(singleton=1),
          database_uuid TEXT NOT NULL UNIQUE,
          schema_identity TEXT NOT NULL,
          schema_version_number INTEGER NOT NULL,
          created_by_runtime TEXT NOT NULL,
          created_at_utc TEXT NOT NULL,
          trust_state TEXT NOT NULL
        )
        """
    )


def read_database_identity(connection: sqlite3.Connection) -> DatabaseIdentity | None:
    exists = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (TABLE_NAME,)
    ).fetchone()
    if not exists:
        return None
    row = connection.execute(
        f"SELECT database_uuid,schema_identity,schema_version_number,created_by_runtime,created_at_utc,trust_state FROM {TABLE_NAME} WHERE singleton=1"
    ).fetchone()
    if row is None:
        return None
    return DatabaseIdentity(*row)


def initialize_database_identity(
    connection: sqlite3.Connection,
    *,
    schema_identity: str,
    schema_version_number: int,
    runtime_version: str = PACKAGE_VERSION_FULL,
    trust_state: str = "trusted",
    database_uuid: str | None = None,
) -> DatabaseIdentity:
    ensure_identity_table(connection)
    existing = read_database_identity(connection)
    if existing is not None:
        return existing
    identity = DatabaseIdentity(
        database_uuid=database_uuid or str(uuid.uuid4()),
        schema_identity=schema_identity,
        schema_version_number=int(schema_version_number),
        created_by_runtime=runtime_version,
        created_at_utc=datetime.now(timezone.utc).isoformat(),
        trust_state=trust_state,
    )
    connection.execute(
        f"""
        INSERT INTO {TABLE_NAME}(
          singleton,database_uuid,schema_identity,schema_version_number,
          created_by_runtime,created_at_utc,trust_state
        ) VALUES(1,?,?,?,?,?,?)
        """,
        (
            identity.database_uuid,
            identity.schema_identity,
            identity.schema_version_number,
            identity.created_by_runtime,
            identity.created_at_utc,
            identity.trust_state,
        ),
    )
    return identity


def mark_imported_untrusted(connection: sqlite3.Connection, *, schema_identity: str = "imported") -> DatabaseIdentity:
    identity = initialize_database_identity(
        connection,
        schema_identity=schema_identity,
        schema_version_number=0,
        trust_state="imported_untrusted",
    )
    if identity.trust_state != "imported_untrusted":
        connection.execute(f"UPDATE {TABLE_NAME} SET trust_state='imported_untrusted' WHERE singleton=1")
        identity.trust_state = "imported_untrusted"
    return identity

from contextlib import closing
from latka_jazn.db.runtime_sqlite import connect_runtime_readonly
from latka_jazn.memory.memory_tier_schema import SCHEMA_SQL
from latka_jazn.version import schema_version_compatibility


def inspect_memory_database(path: str | Path) -> dict[str, Any]:
    """Check content, never infer identity from a filename or initialize tables.

    A missing file is a possible future transactional store, not a ready memory.
    An existing unrecognized database must go through an explicit migration.
    """
    database = Path(path).expanduser().resolve()
    result: dict[str, Any] = {
        "path": str(database), "exists": database.exists(), "read_only": True,
        "kind": "missing", "compatible": False, "ready": False, "issues": [],
    }
    if not database.exists():
        return result
    if not database.is_file():
        result.update(kind="invalid", issues=["database_not_file"])
        return result
    try:
        with closing(connect_runtime_readonly(database, timeout_ms=1000)) as con:
            tables = {str(row[0]) for row in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )}
            if "unified_memory_meta" in tables:
                result["kind"] = "native_unified"
            elif "memory_store_meta" in tables:
                row = con.execute(
                    "SELECT value FROM memory_store_meta WHERE key='schema_version'"
                ).fetchone()
                identity = str(row[0]) if row else None
                result["schema_identity"] = identity
                compatible = schema_version_compatibility("memory_tier_store", identity)
                issues: list[str] = []
                if not compatible["compatible"]:
                    issues.append("unsupported_transactional_schema")
                # Compare the canonical structural contract without running its
                # CREATE/INSERT statements against the selected database.
                with closing(sqlite3.connect(":memory:")) as reference:
                    reference.executescript(SCHEMA_SQL)
                    expected = [str(item[0]) for item in reference.execute(
                        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                    )]
                    for table in expected:
                        if table not in tables:
                            issues.append(f"missing_table:{table}")
                            continue
                        columns = {str(item[1]) for item in con.execute(f'PRAGMA table_info("{table}")')}
                        required = {str(item[1]) for item in reference.execute(f'PRAGMA table_info("{table}")')}
                        if not required <= columns:
                            issues.append(f"missing_columns:{table}")
                if [str(item[0]) for item in con.execute("PRAGMA quick_check")] != ["ok"]:
                    issues.append("sqlite_integrity_failed")
                if con.execute("PRAGMA foreign_key_check").fetchone() is not None:
                    issues.append("sqlite_foreign_key_failed")
                result.update(kind="transactional", compatible=not issues, ready=not issues, issues=issues)
                return result
            else:
                result.update(kind="legacy_or_foreign", issues=["unrecognized_memory_schema"])
                return result
        from latka_jazn.memory.unified_memory_runtime import probe_unified_memory_database
        probe = probe_unified_memory_database(database, busy_timeout_ms=1000)
        result.update(
            schema_identity=probe.get("schema_identity"),
            compatible=probe.get("memory_search_ready") is True,
            ready=probe.get("memory_search_ready") is True,
            native_probe=probe,
            issues=list(probe.get("issues") or []),
        )
        if not result["compatible"] and not result["issues"]:
            result["issues"] = ["native_unified_not_ready"]
    except (OSError, sqlite3.Error, ValueError) as exc:
        result.update(kind="invalid", issues=[f"{type(exc).__name__}: {exc}"])
    return result
