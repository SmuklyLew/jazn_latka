from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from latka_jazn.db.runtime_sqlite import (
    connect_runtime_writable, require_safe_sqlite_write, runtime_sqlite_write_guard,
)
from latka_jazn.tools.sqlite_archive_snapshot import create_sqlite_snapshot

from latka_jazn.memory.database_identity import initialize_database_identity, read_database_identity

MIGRATION_ID = "semantic_index"


@dataclass(slots=True)
class MigrationResult:
    applied: bool
    backup_path: str | None
    database_uuid: str
    schema_version_number: int


def migrate(path: Path | str, *, backup: bool = True) -> MigrationResult:
    db_path = Path(path)
    # Refuse a vulnerable existing WAL before backup, opening or mutation.
    # Cooperating writers cannot interleave with the migration.
    with runtime_sqlite_write_guard(db_path):
        require_safe_sqlite_write(db_path)
        return _migrate_guarded(db_path, backup=backup)


def _migrate_guarded(db_path: Path, *, backup: bool) -> MigrationResult:
    backup_path: Path | None = None
    if backup:
        backup_path = db_path.with_suffix(db_path.suffix + ".pre-v15.bak")
        if not backup_path.exists():
            # Copy the committed database view, not just its main file.
            create_sqlite_snapshot(db_path, backup_path)
    connection = connect_runtime_writable(db_path)
    try:
        connection.execute("BEGIN IMMEDIATE")
        identity = read_database_identity(connection)
        if identity is None:
            identity = initialize_database_identity(
                connection,
                schema_identity="jazn_memory",
                schema_version_number=15_000,
            )
            applied = True
        else:
            applied = identity.schema_version_number < 15_000
            if applied:
                connection.execute(
                    "UPDATE jazn_database_identity SET schema_version_number=15000 WHERE singleton=1"
                )
                identity.schema_version_number = 15_000
        connection.execute(
            "CREATE TABLE IF NOT EXISTS semantic_index_state(key TEXT PRIMARY KEY,value TEXT NOT NULL)"
        )
        connection.execute(
            "INSERT INTO semantic_index_state(key,value) VALUES('migration_id',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (MIGRATION_ID,),
        )
        connection.commit()
        return MigrationResult(applied, str(backup_path) if backup_path else None, identity.database_uuid, identity.schema_version_number)
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
