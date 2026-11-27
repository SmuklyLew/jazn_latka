"""F06: portable staging uses a fresh rollback journal, never a live WAL."""
from __future__ import annotations

from contextlib import closing
from pathlib import Path
import sqlite3

import pytest

from latka_jazn.db import runtime_sqlite as policy
from latka_jazn.tools import verified_memory_restore as restore


@pytest.mark.parametrize("fixed", [False, True])
def test_new_portable_database_is_delete_and_source_health_handles_encoded_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fixed: bool,
) -> None:
    monkeypatch.setattr(policy, "sqlite_wal_reset_fix_available", lambda *_a: fixed)
    path = tmp_path / "synthetic # 50% database.sqlite3"
    statements: list[str] = []
    with closing(policy.connect_new_portable_sqlite(path)) as con:
        con.set_trace_callback(statements.append)
        assert con.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
        assert con.execute("PRAGMA synchronous").fetchone()[0] == 2
        assert con.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        con.execute("CREATE TABLE sample(value TEXT)")
        con.execute("INSERT INTO sample VALUES('synthetic')")
        con.commit()
    assert not any("checkpoint" in statement.lower() for statement in statements)
    assert not any(path.with_name(path.name + suffix).exists() for suffix in ("-wal", "-shm", "-journal"))
    before = path.read_bytes()
    assert restore._sqlite_health(path)["ok"] is True
    with closing(policy.connect_runtime_readonly(path)) as con:
        assert con.execute("SELECT value FROM sample").fetchone()[0] == "synthetic"
        with pytest.raises(sqlite3.OperationalError):
            con.execute("UPDATE sample SET value='modified'")
    assert path.read_bytes() == before


def test_portable_creation_refuses_existing_wal_without_opening(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "existing.sqlite3"
    with closing(sqlite3.connect(path)) as con:
        assert con.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
        con.execute("CREATE TABLE sample(value TEXT)")
        con.commit()
    before = path.read_bytes()

    def forbidden(*_args, **_kwargs):
        pytest.fail("existing database must not reach sqlite open")

    monkeypatch.setattr(sqlite3, "connect", forbidden)
    with pytest.raises(FileExistsError):
        policy.connect_new_portable_sqlite(path)
    assert path.read_bytes() == before


@pytest.mark.parametrize("suffix", ["-wal", "-shm", "-journal"])
def test_portable_creation_refuses_orphan_sidecar(tmp_path: Path, suffix: str) -> None:
    path = tmp_path / "staging.sqlite3"
    sidecar = path.with_name(path.name + suffix)
    sidecar.write_bytes(b"synthetic evidence")
    with pytest.raises(sqlite3.OperationalError, match="portable_sqlite_existing_sidecar"):
        policy.connect_new_portable_sqlite(path)
    assert not path.exists()
    assert sidecar.read_bytes() == b"synthetic evidence"
