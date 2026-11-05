"""Writable MEMORY entry points must not bypass the central WAL refusal."""
from contextlib import closing
import sqlite3

import pytest

from latka_jazn.db import runtime_sqlite as database
from latka_jazn.memory.html_memory_ingest import _checkpoint_database, _settle_database
from latka_jazn.tools.memory_rebuild_app.unified_memory import UnifiedMemoryDatabase
from latka_jazn.tools.memory_rebuild_app.sqlite_utils import ClosingSQLiteConnection


@pytest.mark.parametrize("operation", ["unified_connect", "html_checkpoint", "html_settle"])
def test_memory_writer_refuses_existing_wal_before_open(tmp_path, monkeypatch, operation):
    path = tmp_path / "synthetic.sqlite3"
    with closing(sqlite3.connect(path)) as con:
        assert con.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
        con.execute("CREATE TABLE sample(value)")
        con.commit()
    before = path.read_bytes()
    monkeypatch.setattr(database, "sqlite_wal_reset_fix_available", lambda *_: False)
    def forbidden(*args, **kwargs):
        pytest.fail("unsafe MEMORY WAL reached a writable sqlite3.connect")
    monkeypatch.setattr(database.sqlite3, "connect", forbidden)
    with pytest.raises(sqlite3.OperationalError, match="unsafe_existing_wal_requires_fixed_sqlite"):
        if operation == "unified_connect":
            with closing(UnifiedMemoryDatabase(path).connect()):
                pass
        elif operation == "html_checkpoint":
            _checkpoint_database(path)
        else:
            _settle_database(path)
    assert path.read_bytes() == before


@pytest.mark.parametrize("read_only", [False, True])
def test_central_connection_preserves_closing_factory(tmp_path, read_only):
    path = tmp_path / "synthetic.sqlite3"
    with closing(database.connect_runtime_writable(path)) as initial:
        with initial:
            initial.execute("CREATE TABLE sample(value)")
    connect = database.connect_runtime_readonly if read_only else database.connect_runtime_writable
    with connect(path, factory=ClosingSQLiteConnection) as con:
        assert isinstance(con, ClosingSQLiteConnection)
        assert con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        con.execute("SELECT 1")
