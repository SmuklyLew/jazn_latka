"""Vulnerable SQLite must refuse existing WAL before a writable open."""
from contextlib import closing
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

from latka_jazn.db import runtime_sqlite as database


def make_wal(path):
    with closing(sqlite3.connect(path)) as con:
        assert con.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
        con.execute("CREATE TABLE sample(value TEXT)")
        con.execute("INSERT INTO sample VALUES('synthetic')")
        con.commit()


def test_existing_wal_refused_before_sqlite_open_and_bytes_preserved(tmp_path, monkeypatch):
    path = tmp_path / "synthetic.sqlite3"
    make_wal(path)
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    monkeypatch.setattr(database, "sqlite_wal_reset_fix_available", lambda *_: False)

    def unexpected(*args, **kwargs):
        pytest.fail("Existing unsafe WAL was opened through SQLite")

    monkeypatch.setattr(database.sqlite3, "connect", unexpected)
    with pytest.raises(sqlite3.OperationalError, match="unsafe_existing_wal_requires_fixed_sqlite"):
        database.connect_runtime_writable(path)
    after = {p.name: p.read_bytes() for p in tmp_path.iterdir()
             if not p.name.endswith(".runtime-write.lock")}
    assert after == before


def test_fixed_library_can_keep_existing_wal(tmp_path, monkeypatch):
    path = tmp_path / "synthetic.sqlite3"
    make_wal(path)
    monkeypatch.setattr(database, "sqlite_wal_reset_fix_available", lambda *_: True)
    con = database.connect_runtime_writable(path)
    try:
        assert con.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert con.execute("SELECT value FROM sample").fetchone()[0] == "synthetic"
    finally:
        con.close()


def test_new_and_rollback_databases_remain_writable(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "sqlite_wal_reset_fix_available", lambda *_: False)
    path = tmp_path / "new.sqlite3"
    for _ in range(2):
        con = database.connect_runtime_writable(path)
        try:
            assert con.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
            with con:
                con.execute("CREATE TABLE IF NOT EXISTS sample(value)")
                con.execute("INSERT INTO sample VALUES(1)")
        finally:
            con.close()
    with closing(sqlite3.connect(path)) as check:
        assert check.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert list(check.execute("PRAGMA foreign_key_check")) == []
        assert check.execute("SELECT COUNT(*) FROM sample").fetchone()[0] == 2


def test_gate_does_not_hide_permission_errors(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "sqlite_wal_reset_fix_available", lambda *_: False)
    original = Path.open
    path = tmp_path / "denied.sqlite3"

    def denied(self, *args, **kwargs):
        if self == path:
            raise PermissionError("synthetic denial")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", denied)
    with pytest.raises(PermissionError, match="synthetic denial"):
        database.require_safe_sqlite_write(path)


def test_diagnostic_does_not_claim_global_writer_coverage():
    status = database.runtime_sqlite_capabilities()
    assert status["mitigation_scope"] == "central_runtime_writable_connections_only"
    assert status["existing_wal_on_unfixed_sqlite"] == "refuse_before_writable_open"
    assert status["all_sqlite_writers_verified"] is False


def test_multiple_process_writers_keep_rollback_database_integrity(tmp_path):
    path = tmp_path / "shared.sqlite3"
    worker = """
import sys
from latka_jazn.db.runtime_sqlite import connect_runtime_writable,runtime_sqlite_write_guard
p=sys.argv[1]
c=connect_runtime_writable(p)
try:
    with runtime_sqlite_write_guard(p),c:
        c.execute('CREATE TABLE IF NOT EXISTS sample(worker, value)')
        c.executemany('INSERT INTO sample VALUES(?,?)',[(sys.argv[2],i) for i in range(50)])
finally:c.close()
"""
    processes = [subprocess.Popen([sys.executable, "-X", "utf8", "-c", worker,
                                   str(path), str(i)], stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, text=True) for i in range(3)]
    outcomes = [p.communicate(timeout=30) for p in processes]
    assert [p.returncode for p in processes] == [0, 0, 0], outcomes
    with closing(sqlite3.connect(path)) as check:
        assert check.execute("SELECT COUNT(*) FROM sample").fetchone()[0] == 150
        assert check.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert list(check.execute("PRAGMA foreign_key_check")) == []


def test_rebuild_store_uses_central_safe_journal_policy(tmp_path):
    from latka_jazn.tools.memory_rebuild_store import Store
    path = tmp_path / "rebuild.sqlite3"
    schema = "CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT)"
    with Store(path, schema, "meta", "synthetic/v1") as store:
        assert store.con.execute("PRAGMA journal_mode").fetchone()[0].upper() == database.runtime_sqlite_journal_mode()
        assert store.con.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert store.con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_rebuild_store_refuses_existing_unsafe_wal_without_conversion(tmp_path, monkeypatch):
    from latka_jazn.tools.memory_rebuild_store import Store
    path = tmp_path / "rebuild.sqlite3"
    make_wal(path)
    before = path.read_bytes()
    monkeypatch.setattr(database, "sqlite_wal_reset_fix_available", lambda *_: False)
    with pytest.raises(sqlite3.OperationalError, match="unsafe_existing_wal"):
        Store(path, "CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT)", "meta", "synthetic/v1")
    assert path.read_bytes() == before


def test_archive_and_rebuild_share_the_same_safe_journal_policy(tmp_path):
    from latka_jazn.tools.chat_export_store import ChatExportArchiveStore
    from latka_jazn.tools.memory_rebuild_store import Store
    path = tmp_path / "unified.sqlite3"
    with ChatExportArchiveStore(path) as archive:
        assert archive.con.execute("PRAGMA journal_mode").fetchone()[0].upper() == database.runtime_sqlite_journal_mode()
    with Store(path, "CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT)", "meta", "synthetic/v1") as rebuilt:
        assert rebuilt.con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert rebuilt.con.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_source_mirror_uses_the_same_safe_journal_policy(tmp_path):
    from latka_jazn.tools.memory_rebuild_app.source_fidelity import _connect
    with closing(_connect(tmp_path / "mirror.sqlite3")) as con:
        assert con.execute("PRAGMA journal_mode").fetchone()[0].upper() == database.runtime_sqlite_journal_mode()
        assert con.execute("PRAGMA foreign_keys").fetchone()[0] == 1
