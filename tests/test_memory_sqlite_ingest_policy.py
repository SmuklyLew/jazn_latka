"""Synthetic V116 regression: HTML ingest and unified rebuild respect central SQLite safety.

These tests do not open private MEMORY, live daemons, or existing operator databases.
"""
from __future__ import annotations

from contextlib import closing
from pathlib import Path
import sqlite3

import pytest

from latka_jazn.db import runtime_sqlite as policy
from latka_jazn.memory import html_memory_ingest as html_ingest
from latka_jazn.tools.memory_rebuild_app.unified_core import UnifiedCoreMixin


def _make_wal(path: Path) -> None:
    with closing(sqlite3.connect(path)) as connection:
        connection.execute("CREATE TABLE sample(value TEXT NOT NULL)")
        assert connection.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
        connection.execute("INSERT INTO sample VALUES('synthetic')")
        connection.commit()


def _unified(path: Path) -> UnifiedCoreMixin:
    instance = UnifiedCoreMixin()
    instance.path = path
    return instance


def test_unified_memory_new_database_uses_central_rollback_mode(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(policy, "sqlite_wal_reset_fix_available", lambda *_: False)
    with _unified(tmp_path / "unified.sqlite3").connect() as connection:
        assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert connection.execute("PRAGMA busy_timeout").fetchone()[0] == 30000
        assert connection.row_factory is sqlite3.Row
        connection.execute("CREATE TABLE sample(value TEXT NOT NULL)")
        connection.execute("INSERT INTO sample VALUES('synthetic')")
        connection.commit()
    with _unified(tmp_path / "unified.sqlite3").connect(read_only=True) as connection:
        assert connection.execute("PRAGMA query_only").fetchone()[0] == 1
        assert connection.execute("SELECT value FROM sample").fetchone()[0] == "synthetic"


def test_unified_memory_refuses_unsafe_existing_wal_without_changes(tmp_path, monkeypatch) -> None:
    path = tmp_path / "existing.sqlite3"
    _make_wal(path)
    original = path.read_bytes()
    monkeypatch.setattr(policy, "sqlite_wal_reset_fix_available", lambda *_: False)
    with pytest.raises(sqlite3.OperationalError, match="unsafe_existing_wal_requires_fixed_sqlite"):
        _unified(path).connect()
    assert path.read_bytes() == original


@pytest.mark.parametrize("operation", [html_ingest._checkpoint_database, html_ingest._settle_database])
def test_html_memory_maintenance_rejects_unsafe_existing_wal(
    tmp_path, monkeypatch, operation
) -> None:
    path = tmp_path / "existing.sqlite3"
    _make_wal(path)
    original = path.read_bytes()
    monkeypatch.setattr(policy, "sqlite_wal_reset_fix_available", lambda *_: False)
    with pytest.raises(sqlite3.OperationalError, match="unsafe_existing_wal_requires_fixed_sqlite"):
        operation(path)
    assert path.read_bytes() == original


def test_html_memory_backup_uses_readonly_source_and_preserves_source(tmp_path) -> None:
    source = tmp_path / "source.sqlite3"
    destination = tmp_path / "backup.sqlite3"
    with closing(sqlite3.connect(source)) as connection:
        connection.execute("CREATE TABLE sample(value TEXT NOT NULL)")
        connection.execute("INSERT INTO sample VALUES('synthetic')")
        connection.commit()
    original = source.read_bytes()
    result = html_ingest._sqlite_backup(source, destination)
    assert result["ok"] is True
    assert source.read_bytes() == original
    with closing(sqlite3.connect(destination)) as connection:
        assert connection.execute("SELECT value FROM sample").fetchone()[0] == "synthetic"
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
