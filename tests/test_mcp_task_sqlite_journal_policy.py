"""MCP task persistence obeys the central WAL-reset safety policy."""
from contextlib import closing
import sqlite3

import pytest

from latka_jazn.db import runtime_sqlite as database
from latka_jazn.mcp.task_resume import McpTaskStore


def test_task_store_uses_rollback_on_unfixed_sqlite(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "sqlite_wal_reset_fix_available", lambda *_: False)
    store = McpTaskStore(tmp_path)
    record = store.create_or_get(daemon_request_id="synthetic-policy-request")
    assert McpTaskStore(tmp_path).get(record.task_id) is not None
    with closing(sqlite3.connect(store.db_path)) as con:
        assert con.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
        assert con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert list(con.execute("PRAGMA foreign_key_check")) == []


def test_task_store_refuses_existing_unsafe_wal_before_open(tmp_path, monkeypatch):
    workspace = tmp_path / "task-workspace"
    workspace.mkdir()
    monkeypatch.setenv("JAZN_RUNTIME_WORKSPACE_DIR", str(workspace))
    path = workspace / "mcp_tasks.sqlite3"
    with closing(sqlite3.connect(path)) as con:
        assert con.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
        con.execute("CREATE TABLE synthetic(value)")
        con.commit()
    before = path.read_bytes()
    monkeypatch.setattr(database, "sqlite_wal_reset_fix_available", lambda *_: False)
    def forbidden(*args, **kwargs):
        pytest.fail("unsafe existing task WAL reached sqlite3.connect")
    monkeypatch.setattr(database.sqlite3, "connect", forbidden)
    with pytest.raises(sqlite3.OperationalError, match="unsafe_existing_wal_requires_fixed_sqlite"):
        McpTaskStore(tmp_path)
    assert path.read_bytes() == before


def test_task_store_keeps_wal_available_on_fixed_library(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "sqlite_wal_reset_fix_available", lambda *_: True)
    store = McpTaskStore(tmp_path)
    store.create_or_get(daemon_request_id="synthetic-fixed-request")
    with closing(sqlite3.connect(store.db_path)) as con:
        assert con.execute("PRAGMA journal_mode").fetchone()[0] == "wal"


@pytest.mark.parametrize("uri", [database.readonly_sqlite_uri, database.writable_sqlite_uri])
def test_extended_windows_path_is_not_encoded_as_uri_authority(monkeypatch, uri):
    # Scope the simulated Windows namespace to the SQLite module. Patching
    # pathlib.Path.resolve globally would also redirect durable pytest receipts
    # emitted before fixture teardown, correctly tripping their path guard.
    class NamespacePath:
        def __init__(self, value):
            pass
        def expanduser(self):
            return self
        def resolve(self):
            return "//?/D:/synthetic folder/task.sqlite3"
    monkeypatch.setattr(database, "Path", NamespacePath)
    assert uri("ignored").startswith("file:D:/synthetic%20folder/task.sqlite3?mode=")
