"""Release-only version changes never prove memory content changed or remained stable.

All databases are synthetic and temporary; no private MEMORY is opened.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from latka_jazn.memory.normalization_sidecar import (
    FINGERPRINT_CONTRACT_VERSION, MemoryNormalizationSidecar,
    SCHEMA_VERSION, _physical_sqlite_state, _relevant_logical_fingerprint,
)


def _fixture(tmp_path: Path, *, with_fingerprint: bool = True) -> MemoryNormalizationSidecar:
    source = tmp_path / "source.sqlite3"
    sidecar = tmp_path / "sidecar.sqlite3"
    with sqlite3.connect(source) as connection:
        connection.execute("CREATE TABLE procedural_rules (rule_id TEXT, trigger TEXT, action TEXT, reason TEXT, priority INTEGER, source TEXT, created_at_utc TEXT)")
        connection.execute("INSERT INTO procedural_rules VALUES ('r1', 't', 'a', 'why', 1, 'test', '2026-01-01')")
    logical = _relevant_logical_fingerprint(source, include_content=True)
    physical = _physical_sqlite_state(source)
    with sqlite3.connect(sidecar) as connection:
        connection.execute("CREATE TABLE actors (actor_id TEXT)")
        connection.execute("CREATE TABLE normalized_memory_items (item_id TEXT)")
        connection.execute("CREATE TABLE wake_state_snapshots (snapshot_id TEXT)")
        connection.execute("""CREATE TABLE normalization_runs (
            run_id TEXT, status TEXT, ended_at_utc TEXT, schema_version TEXT,
            runtime_version TEXT, coverage_complete INTEGER, expected_item_count INTEGER,
            normalized_item_count INTEGER, fingerprint_contract_version TEXT,
            relevant_content_sha256 TEXT, relevant_schema_sha256 TEXT,
            relevant_row_count INTEGER, relevant_revision TEXT,
            source_db_path TEXT, source_db_size INTEGER, source_db_mtime_ns INTEGER,
            source_db_wal_size INTEGER, source_db_wal_mtime_ns INTEGER,
            source_db_shm_present INTEGER, source_db_sha256 TEXT,
            started_at_utc TEXT, dry_run INTEGER
        )""")
        connection.execute(
            """INSERT INTO normalization_runs VALUES (
            'old', 'ok', '2026-08-24T00:00:00Z', ?, '16.2.3', 1, 1, 1,
            ?, ?, ?, ?, ?, ?, ?, ?, 0, NULL, 0, NULL, '2026-08-24T00:00:00Z', 0
            )""",
            (SCHEMA_VERSION,
             FINGERPRINT_CONTRACT_VERSION if with_fingerprint else None,
             logical["relevant_content_sha256"] if with_fingerprint else None,
             logical["relevant_schema_sha256"] if with_fingerprint else None,
             logical["relevant_row_count"] if with_fingerprint else None,
             logical["relevant_revision"] if with_fingerprint else None,
             str(source),
             physical["source_db_size"],
             physical["source_db_mtime_ns"]),
        )
    return MemoryNormalizationSidecar(
        tmp_path, source_db_path=source, sidecar_db_path=sidecar,
        runtime_version="16.3.25.5.116.0.34.41",
    )


def test_release_bump_requires_deep_evidence_but_does_not_imply_staleness(tmp_path: Path) -> None:
    sidecar = _fixture(tmp_path)
    bounded = sidecar.status()
    assert bounded.status == "normalization_unverified"
    assert bounded.freshness is not None
    assert bounded.freshness["reason"] == "runtime_version_changed_deep_verification_required"
    verified = sidecar.status(deep_verify=True)
    assert verified.status == "ready"
    assert verified.freshness is not None
    assert verified.freshness["invalidates_wake_state"] is False


def test_missing_legacy_fingerprint_stays_fail_closed(tmp_path: Path) -> None:
    sidecar = _fixture(tmp_path, with_fingerprint=False)
    assert sidecar.status().status == "normalization_unverified"
    deep = sidecar.status(deep_verify=True)
    assert deep.status == "normalization_stale"
    assert deep.freshness is not None
    assert deep.freshness["reason"] == "fingerprint_contract_missing"


def test_actual_content_change_invalidates_regardless_of_package_version(tmp_path: Path) -> None:
    sidecar = _fixture(tmp_path)
    with sqlite3.connect(sidecar.source_db_path) as con:
        con.execute("UPDATE procedural_rules SET action='changed' WHERE rule_id='r1'")
    result = sidecar.status(deep_verify=True)
    assert result.status == "source_changed"
    assert result.freshness is not None
    assert result.freshness["relevant_content_changed"] is True
