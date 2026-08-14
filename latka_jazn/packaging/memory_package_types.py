from __future__ import annotations

import json
import os
import sqlite3
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from latka_jazn.core.package_integrity_manifest import sha256_file
from latka_jazn.version import schema_version

MEMORY_PACKAGE_MANIFEST_PATH = "memory/MEMORY_PACKAGE_MANIFEST.json"
MEMORY_MANIFEST_SCHEMA_V1 = "jazn_memory_package_manifest/v1"
MEMORY_MANIFEST_SCHEMA_V2 = "jazn_memory_package_manifest/v2"
MEMORY_FORMAT_VERSION = 2
MEMORY_RUNTIME_COMPATIBILITY_CONTRACT = "jazn_memory_runtime/v1"
MEMORY_ATTACH_SCHEMA_VERSION = schema_version("memory_package_attach")
MEMORY_ATTACH_MARKER_PATH = "workspace_runtime/MEMORY_PACKAGE_CURRENT.json"
SQLITE_HEADER = b"SQLite format 3\x00"
TRANSIENT_DATABASE_SUFFIXES = (
    "-wal", "-shm", ".sqlite-wal", ".sqlite-shm",
    ".sqlite3-wal", ".sqlite3-shm", ".db-wal", ".db-shm",
)
TRUTH_BOUNDARY = (
    "Paczka memory jest zweryfikowanym transportem danych, nigdy active_root. "
    "created_with_runtime jest proweniencją. Bezpośrednie użycie baz nadal podlega "
    "database identity, recovery i memory truth gates; attach nie promuje L2/L3."
)


@dataclass(slots=True)
class MemoryAttachResult:
    ok: bool
    state: str
    runtime_root: str
    report: dict[str, Any]
    pending: bool = False
    exit_code: int = 0
    schema_version: str = MEMORY_ATTACH_SCHEMA_VERSION
    truth_boundary: str = TRUTH_BOUNDARY

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def read_json(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError):
        return None
    return payload if isinstance(payload, dict) else None


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".tmp-{uuid.uuid4().hex}")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def sqlite_file(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            return handle.read(len(SQLITE_HEADER)) == SQLITE_HEADER
    except OSError:
        return False


def _database_identity(connection: sqlite3.Connection) -> dict[str, Any] | None:
    exists = connection.execute(
        "SELECT 1 FROM sqlite_schema WHERE type='table' AND name='jazn_database_identity'"
    ).fetchone()
    if not exists:
        return None
    row = connection.execute(
        "SELECT database_uuid,schema_identity,schema_version_number,created_by_runtime,"
        "created_at_utc,trust_state FROM jazn_database_identity WHERE singleton=1"
    ).fetchone()
    if row is None:
        return None
    return {
        "database_uuid": str(row[0]), "schema_identity": str(row[1]),
        "schema_version_number": int(row[2]), "created_by_runtime": str(row[3]),
        "created_at_utc": str(row[4]), "trust_state": str(row[5]),
    }


def inspect_sqlite_memory_file(path: Path, *, legacy: bool = False) -> dict[str, Any]:
    path = Path(path).resolve()
    with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=30.0) as connection:
        connection.execute("PRAGMA query_only=ON")
        connection.execute("PRAGMA busy_timeout=30000")
        quick = str(connection.execute("PRAGMA quick_check(1)").fetchone()[0])
        foreign_rows = [] if legacy else list(connection.execute("PRAGMA foreign_key_check").fetchmany(100))
        user_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        application_id = int(connection.execute("PRAGMA application_id").fetchone()[0])
        identity = _database_identity(connection)
        table_count = int(connection.execute("SELECT COUNT(*) FROM sqlite_schema WHERE type='table'").fetchone()[0])
    return {
        "ok": quick == "ok" and (legacy or not foreign_rows), "path": str(path),
        "size_bytes": path.stat().st_size, "sha256": sha256_file(path), "quick_check": quick,
        "foreign_key_error_count": len(foreign_rows), "user_version": user_version,
        "application_id": application_id, "database_identity": identity, "table_count": table_count,
    }
