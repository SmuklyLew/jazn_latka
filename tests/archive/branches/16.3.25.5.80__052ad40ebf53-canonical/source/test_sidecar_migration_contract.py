from __future__ import annotations

from pathlib import Path
import sqlite3

from latka_jazn.config import JaznConfig
from latka_jazn.memory.normalization_sidecar import MemoryNormalizationSidecar
from latka_jazn.memory.wake_state_runtime import WakeStateRuntimeBridge


def test_legacy_mixed_audit_sidecar_is_copied_without_mutating_source(tmp_path: Path) -> None:
    root = tmp_path / "runtime"
    cfg = JaznConfig(root=root)
    legacy = cfg.audit_db_path
    legacy.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(legacy) as con:
        con.executescript(
            """
            CREATE TABLE sidecar_meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE normalization_runs(run_id TEXT PRIMARY KEY);
            CREATE TABLE actors(actor_id TEXT PRIMARY KEY);
            CREATE TABLE normalized_memory_items(item_id TEXT PRIMARY KEY);
            CREATE TABLE wake_state_snapshots(
              snapshot_id TEXT PRIMARY KEY,
              created_at_utc TEXT NOT NULL,
              source_run_id TEXT,
              source_db_sha256 TEXT,
              snapshot_json TEXT NOT NULL,
              snapshot_sha256 TEXT NOT NULL,
              validation_status TEXT NOT NULL,
              active INTEGER NOT NULL,
              schema_version TEXT NOT NULL
            );
            INSERT INTO wake_state_snapshots VALUES(
              'wake-legacy','2026-07-27T10:00:00+00:00','run-1',NULL,
              '{}','44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a',
              'valid',1,'wake_state_snapshot/v1'
            );
            CREATE TABLE audit_runtime_events(id INTEGER PRIMARY KEY, payload TEXT);
            INSERT INTO audit_runtime_events(payload) VALUES('must stay only in source');
            """
        )
    before = legacy.read_bytes()

    sidecar = MemoryNormalizationSidecar(root)
    sidecar.ensure_schema()

    assert cfg.normalization_sidecar_db_path.is_file()
    assert legacy.read_bytes() == before
    with sqlite3.connect(cfg.normalization_sidecar_db_path) as con:
        tables = {row[0] for row in con.execute("SELECT name FROM sqlite_schema WHERE type='table'")}
        assert "wake_state_snapshots" in tables
        assert "audit_runtime_events" not in tables
        assert con.execute("SELECT COUNT(*) FROM wake_state_snapshots").fetchone()[0] == 1
        source = con.execute(
            "SELECT value FROM sidecar_meta WHERE key='legacy_sidecar_migration_source'"
        ).fetchone()[0]
        assert source == str(legacy.resolve())


def test_wake_state_reports_missing_schema_explicitly(tmp_path: Path) -> None:
    cfg = JaznConfig(root=tmp_path / "runtime")
    cfg.normalization_sidecar_db_path.parent.mkdir(parents=True, exist_ok=True)
    sqlite3.connect(cfg.normalization_sidecar_db_path).close()
    status = WakeStateRuntimeBridge(cfg).load()
    assert status.status == "sidecar_schema_missing"
    assert any("wake_state_snapshots" in error for error in status.errors)
