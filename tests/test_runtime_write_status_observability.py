from __future__ import annotations

import sqlite3
from pathlib import Path
from types import SimpleNamespace

from latka_jazn.memory.runtime_write_access_contract import (
    _sqlite_status,
    build_runtime_write_access_status,
)


def _make_database(path: Path, *, rows: int) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE audit_rows (id INTEGER PRIMARY KEY)")
        connection.executemany(
            "INSERT INTO audit_rows (id) VALUES (?)",
            ((index,) for index in range(1, rows + 1)),
        )


def test_metadata_only_reports_unmeasured_counts_as_unknown(tmp_path: Path) -> None:
    database = tmp_path / "runtime_audit.sqlite3"
    _make_database(database, rows=3)

    metadata = _sqlite_status(database, deep_verify=False)

    assert metadata["integrity"] == "ready_metadata_only"
    assert metadata["record_count"] is None
    assert metadata["record_count_measured"] is False
    assert metadata["table_count"] == 1


def test_deep_verification_distinguishes_zero_from_nonzero(tmp_path: Path) -> None:
    empty_db = tmp_path / "empty.sqlite3"
    populated_db = tmp_path / "populated.sqlite3"
    _make_database(empty_db, rows=0)
    _make_database(populated_db, rows=2)

    empty = _sqlite_status(empty_db, deep_verify=True)
    populated = _sqlite_status(populated_db, deep_verify=True)

    assert empty["integrity"] == "ok"
    assert empty["record_count_measured"] is True
    assert empty["record_count"] == 0
    assert populated["integrity"] == "ok"
    assert populated["record_count_measured"] is True
    assert populated["record_count"] == 2


def test_runtime_status_does_not_claim_unmeasured_writes(tmp_path: Path) -> None:
    memory_db = tmp_path / "runtime_memory.sqlite3"
    audit_db = tmp_path / "runtime_audit.sqlite3"
    _make_database(memory_db, rows=0)
    _make_database(audit_db, rows=4)
    config = SimpleNamespace(
        runtime_memory_storage_root=tmp_path,
        memory_db_path_readonly=memory_db,
        audit_db_path_readonly=audit_db,
    )

    metadata = build_runtime_write_access_status(
        config, writes_enabled=False, deep_verify=False
    )
    assert metadata.ok is True
    assert metadata.status == "ready_metadata_only"
    assert metadata.write_capable is True
    assert metadata.record_counts_measured is False
    assert metadata.memory_record_count is None
    assert metadata.audit_record_count is None
    assert metadata.writes_observed is None
    assert metadata.to_dict()["writes_observed"] is None

    deep = build_runtime_write_access_status(
        config, writes_enabled=False, deep_verify=True
    )
    assert deep.ok is True
    assert deep.record_counts_measured is True
    assert deep.memory_record_count == 0
    assert deep.audit_record_count == 4
    assert deep.writes_observed is True
    assert deep.writes_enabled is False


def test_missing_databases_are_not_mistaken_for_empty_ones(tmp_path: Path) -> None:
    config = SimpleNamespace(
        runtime_memory_storage_root=tmp_path,
        memory_db_path_readonly=tmp_path / "missing_memory.sqlite3",
        audit_db_path_readonly=tmp_path / "missing_audit.sqlite3",
    )

    status = build_runtime_write_access_status(
        config, deep_verify=False
    )

    assert status.status == "missing_can_initialize"
    assert status.record_counts_measured is False
    assert status.writes_observed is None
    assert status.memory_record_count is None
    assert status.audit_record_count is None
