from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sqlite3

from latka_jazn.audit.audit_context_store import AuditContextStore
from latka_jazn.db.runtime_sqlite import (
    connect_runtime_readonly,
    connect_runtime_writable,
    runtime_sqlite_capabilities,
    runtime_sqlite_journal_mode,
    runtime_sqlite_write_guard,
    sqlite_error_diagnostics,
    sqlite_wal_reset_fix_available,
)
from latka_jazn.memory.store import MemoryStore


def test_sqlite_wal_reset_fix_version_matrix() -> None:
    assert sqlite_wal_reset_fix_available((3, 51, 2)) is False
    assert sqlite_wal_reset_fix_available((3, 51, 3)) is True
    assert sqlite_wal_reset_fix_available((3, 44, 5)) is False
    assert sqlite_wal_reset_fix_available((3, 44, 6)) is True
    assert sqlite_wal_reset_fix_available((3, 50, 6)) is False
    assert sqlite_wal_reset_fix_available((3, 50, 7)) is True
    assert sqlite_wal_reset_fix_available((3, 53, 4)) is True


def test_runtime_sqlite_journal_mode_avoids_wal_on_affected_builds() -> None:
    assert runtime_sqlite_journal_mode((3, 46, 1)) == "DELETE"
    assert runtime_sqlite_journal_mode((3, 50, 6)) == "DELETE"
    assert runtime_sqlite_journal_mode((3, 50, 7)) == "WAL"
    assert runtime_sqlite_journal_mode((3, 51, 3)) == "WAL"
    assert runtime_sqlite_journal_mode((3, 53, 4)) == "WAL"


def test_runtime_sqlite_capabilities_disclose_loaded_library_and_mitigation() -> None:
    payload = runtime_sqlite_capabilities()
    assert payload["sqlite_version"] == sqlite3.sqlite_version
    assert payload["sqlite_threadsafety"] == sqlite3.threadsafety
    assert payload["runtime_writer_serialization"] == "cross_process_file_lock+process_rlock"
    assert payload["selected_journal_mode"] == runtime_sqlite_journal_mode()
    assert payload["wal_reset_mitigation_required"] is (not payload["wal_reset_fix_available"])
    assert payload["wal_reset_mitigation_active"] is (not payload["wal_reset_fix_available"])


def test_sqlite_error_diagnostics_preserve_native_code_and_name() -> None:
    con = sqlite3.connect(":memory:")
    try:
        try:
            con.execute("SELECT * FROM definitely_missing_table").fetchall()
        except sqlite3.Error as exc:
            payload = sqlite_error_diagnostics(exc, operation="test-query")
        else:  # pragma: no cover
            raise AssertionError("expected sqlite error")
    finally:
        con.close()
    assert payload["exception_type"] == "OperationalError"
    assert payload["sqlite_errorcode"] is not None
    assert str(payload["sqlite_errorname"]).startswith("SQLITE_")
    assert payload["operation"] == "test-query"


def test_runtime_writable_connection_uses_safe_journal_mode_and_foreign_keys(tmp_path: Path) -> None:
    path = tmp_path / "runtime.sqlite3"
    con = connect_runtime_writable(path, synchronous="FULL")
    try:
        assert str(con.execute("PRAGMA journal_mode").fetchone()[0]).upper() == runtime_sqlite_journal_mode()
        assert int(con.execute("PRAGMA foreign_keys").fetchone()[0]) == 1
        assert int(con.execute("PRAGMA busy_timeout").fetchone()[0]) >= 30_000
        with runtime_sqlite_write_guard(path), con:
            con.execute("CREATE TABLE sample(id INTEGER PRIMARY KEY, value TEXT NOT NULL)")
            con.execute("INSERT INTO sample(value) VALUES('ok')")
    finally:
        con.close()

    read = connect_runtime_readonly(path)
    try:
        assert int(read.execute("PRAGMA query_only").fetchone()[0]) == 1
        assert read.execute("SELECT value FROM sample").fetchone()[0] == "ok"
    finally:
        read.close()



def test_runtime_stores_do_not_override_central_journal_policy(tmp_path: Path) -> None:
    memory_path = tmp_path / "runtime_memory.sqlite3"
    memory = MemoryStore(memory_path)
    try:
        assert str(memory.con.execute("PRAGMA journal_mode").fetchone()[0]).upper() == runtime_sqlite_journal_mode()
    finally:
        memory.close()

    audit_path = tmp_path / "runtime_audit.sqlite3"
    audit = AuditContextStore(audit_path)
    try:
        assert str(audit.con.execute("PRAGMA journal_mode").fetchone()[0]).upper() == runtime_sqlite_journal_mode()
    finally:
        audit.close()

def test_memory_store_concurrent_sessions_serialize_writes_and_keep_integrity(tmp_path: Path) -> None:
    path = tmp_path / "runtime_memory.sqlite3"

    def write_batch(worker: int) -> None:
        store = MemoryStore(path)
        try:
            for index in range(20):
                store.add_event(
                    "concurrency_test",
                    {"worker": worker, "index": index},
                    source="test_runtime_sqlite_hardening",
                )
        finally:
            store.close()

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(write_batch, range(8)))

    con = connect_runtime_readonly(path)
    try:
        assert con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert list(con.execute("PRAGMA foreign_key_check")) == []
        count = con.execute("SELECT COUNT(*) FROM events WHERE event_type='concurrency_test'").fetchone()[0]
        assert count == 160
    finally:
        con.close()


def test_runtime_write_guard_is_reentrant_for_same_database_on_same_thread(tmp_path: Path) -> None:
    path = tmp_path / "nested.sqlite3"
    with runtime_sqlite_write_guard(path, timeout_ms=1000):
        con = connect_runtime_writable(path, timeout_ms=1000)
        try:
            with runtime_sqlite_write_guard(path, timeout_ms=1000), con:
                con.execute("CREATE TABLE nested_ok(id INTEGER PRIMARY KEY)")
        finally:
            con.close()
    read = connect_runtime_readonly(path)
    try:
        assert "nested_ok" in {row[0] for row in read.execute("SELECT name FROM sqlite_schema WHERE type='table'")}
    finally:
        read.close()
