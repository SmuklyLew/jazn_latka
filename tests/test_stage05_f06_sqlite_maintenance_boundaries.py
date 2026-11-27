"""F06: isolated maintenance paths obey WAL policy and read-only source boundaries."""
from __future__ import annotations

from contextlib import closing
from pathlib import Path
import sqlite3

import pytest

from latka_jazn.db import runtime_sqlite as policy
from latka_jazn.memory.migrations.semantic_index import migrate
from latka_jazn.tools import memory_restore_storage as restore


def _database(path: Path, *, wal: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path)) as con:
        if wal:
            assert con.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
        con.execute("CREATE TABLE sample(value TEXT)")
        con.execute("INSERT INTO sample VALUES('synthetic')")
        con.commit()


@pytest.mark.parametrize("backup", [True, False])
def test_migration_refuses_vulnerable_wal_before_backup_or_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, backup: bool,
) -> None:
    path = tmp_path / "source.sqlite3"
    _database(path, wal=True)
    before = path.read_bytes()
    monkeypatch.setattr(policy, "sqlite_wal_reset_fix_available", lambda *_a: False)
    def forbidden(*_args, **_kwargs):
        pytest.fail("unsafe database reached SQLite open")
    monkeypatch.setattr(sqlite3, "connect", forbidden)
    with pytest.raises(sqlite3.OperationalError, match="unsafe_existing_wal_requires_fixed_sqlite"):
        migrate(path, backup=backup)
    assert path.read_bytes() == before
    assert not path.with_suffix(path.suffix + ".pre-v15.bak").exists()


def test_migration_uses_safe_mode_and_consistent_backup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "source.sqlite3"
    _database(path)
    monkeypatch.setattr(policy, "sqlite_wal_reset_fix_available", lambda *_a: False)
    result = migrate(path)
    assert result.applied and result.backup_path is not None
    with closing(sqlite3.connect(path)) as con:
        assert con.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
        assert con.execute("SELECT value FROM semantic_index_state WHERE key='migration_id'").fetchone()[0] == "semantic_index"
        assert con.execute("SELECT value FROM sample").fetchone()[0] == "synthetic"
    with closing(sqlite3.connect(result.backup_path)) as con:
        assert con.execute("SELECT value FROM sample").fetchone()[0] == "synthetic"
        assert con.execute("SELECT COUNT(*) FROM sqlite_master WHERE name='semantic_index_state'").fetchone()[0] == 0


def test_comparison_attach_enforces_readonly_uri_even_without_query_only(tmp_path: Path) -> None:
    path = tmp_path / "synthetic # database.sqlite3"
    _database(path)
    before = path.read_bytes()
    with closing(sqlite3.connect(":memory:", uri=True)) as con:
        restore._attach(con, "old", path)
        assert con.execute("SELECT value FROM old.sample").fetchone()[0] == "synthetic"
        with pytest.raises(sqlite3.OperationalError):
            con.execute("UPDATE old.sample SET value='modified'")
    assert path.read_bytes() == before


def test_backup_refuses_unsafe_existing_destination_before_sqlite_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.sqlite3"
    destination = tmp_path / "backup"
    target = destination / "memory" / "sqlite" / restore.DATABASE_FILENAMES["archive_chats"]
    _database(source)
    _database(target, wal=True)
    source_before, target_before = source.read_bytes(), target.read_bytes()
    monkeypatch.setattr(restore, "resolve_database_paths", lambda _root: {"archive_chats": source})
    monkeypatch.setattr(policy, "sqlite_wal_reset_fix_available", lambda *_a: False)
    def forbidden(*_args, **_kwargs):
        pytest.fail("unsafe backup destination reached SQLite open")
    monkeypatch.setattr(sqlite3, "connect", forbidden)
    with pytest.raises(sqlite3.OperationalError, match="unsafe_existing_wal_requires_fixed_sqlite"):
        restore.backup_database_set(tmp_path, destination)
    assert source.read_bytes() == source_before and target.read_bytes() == target_before
    assert not (destination / "backup_manifest.json").exists()
