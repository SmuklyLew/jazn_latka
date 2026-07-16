from __future__ import annotations

from pathlib import Path
import hashlib
import json
import socket
import sqlite3

import pytest

from latka_jazn import cli
from latka_jazn.config import JaznConfig
from latka_jazn.cli_commands.diagnostics import doctor_payload, status_payload
from latka_jazn.core.runtime_daemon import start_daemon, stop_daemon
from latka_jazn.memory.normalization_sidecar import MemoryNormalizationSidecar
from latka_jazn.memory.runtime_write_access_contract import build_runtime_write_access_status
from latka_jazn.tools.release_staging import create_system_smoke_staging


ROOT = Path(__file__).resolve().parents[1]


def _source(path: Path, count: int = 1, *, bad_fk: bool = False) -> None:
    with sqlite3.connect(path) as con:
        con.executescript(
            """
            CREATE TABLE messages(
              message_id TEXT, conversation_id TEXT, conversation_title TEXT, role TEXT,
              timestamp TEXT, content_text TEXT, content_hash TEXT, first_source_file TEXT,
              first_source_sha256 TEXT, source_refs_json TEXT, created_at TEXT, updated_at TEXT
            );
            CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
            INSERT INTO meta(key,value) VALUES('created_by','isolated-test');
            """
        )
        con.executemany(
            "INSERT INTO messages VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                (
                    f"m{i}", "c1", "Test", "assistant" if i % 2 else "user",
                    f"2026-07-16T10:{i % 60:02d}:00+00:00", f"memory item {i}",
                    hashlib.sha256(f"memory item {i}".encode()).hexdigest(), "source.json", "a" * 64,
                    "[]", "2026-07-16T10:00:00+00:00", "2026-07-16T10:00:00+00:00",
                )
                for i in range(count)
            ],
        )
        if bad_fk:
            con.executescript(
                """
                PRAGMA foreign_keys=OFF;
                CREATE TABLE parent(id INTEGER PRIMARY KEY);
                CREATE TABLE child(parent_id INTEGER REFERENCES parent(id));
                INSERT INTO child(parent_id) VALUES(99);
                """
            )
        con.commit()


def _sidecar(tmp_path: Path, *, count: int = 1, bad_fk: bool = False) -> MemoryNormalizationSidecar:
    source = tmp_path / "source.sqlite3"
    _source(source, count, bad_fk=bad_fk)
    return MemoryNormalizationSidecar(
        tmp_path,
        source_db_path=source,
        sidecar_db_path=tmp_path / "audit.sqlite3",
        runtime_version="v15.0.3.2",
    )


def test_prepare_builds_verified_snapshot_and_is_idempotent(tmp_path: Path) -> None:
    sidecar = _sidecar(tmp_path)
    first = sidecar.prepare().to_dict()
    assert first["status"] == "ready"
    assert first["normalization_performed"] is True
    assert first["snapshot_built"] is True
    snapshot_id = first["wake_state"]["active_snapshot"]["snapshot_id"]

    second = sidecar.prepare().to_dict()
    assert second["status"] == "ready"
    assert second["normalization_performed"] is False
    assert second["snapshot_built"] is False
    assert second["wake_state"]["active_snapshot"]["snapshot_id"] == snapshot_id


def test_source_change_requires_new_run(tmp_path: Path) -> None:
    sidecar = _sidecar(tmp_path)
    first = sidecar.prepare().to_dict()
    with sqlite3.connect(sidecar.source_db_path) as con:
        con.execute(
            "INSERT INTO messages VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            ("m2", "c1", "Test", "user", "2026-07-16T12:00:00+00:00", "changed", "h", None, None, "[]", "x", "x"),
        )
        con.commit()
    assert sidecar.status().status == "source_changed"
    second = sidecar.prepare().to_dict()
    assert second["status"] == "ready"
    assert second["normalization_performed"] is True
    assert second["wake_state"]["active_snapshot"]["source_run_id"] != first["wake_state"]["active_snapshot"]["source_run_id"]


def test_snapshot_hash_mismatch_is_reported(tmp_path: Path) -> None:
    sidecar = _sidecar(tmp_path)
    assert sidecar.prepare().status == "ready"
    with sqlite3.connect(sidecar.sidecar_db_path) as con:
        con.execute("UPDATE wake_state_snapshots SET snapshot_json=snapshot_json || ' '")
        con.commit()
    assert sidecar.wake_state_status(deep_verify=True).status == "snapshot_hash_mismatch"


def test_legacy_multiple_active_rows_are_migrated_to_one(tmp_path: Path) -> None:
    sidecar = _sidecar(tmp_path)
    assert sidecar.prepare().status == "ready"
    with sqlite3.connect(sidecar.sidecar_db_path) as con:
        con.execute("DROP INDEX uq_wake_state_single_active")
        row = con.execute("SELECT * FROM wake_state_snapshots WHERE active=1").fetchone()
        con.execute(
            "INSERT INTO wake_state_snapshots VALUES(?,?,?,?,?,?,?,?,?)",
            ("legacy-second", row[1], "2099-01-01T00:00:00+00:00", 1, row[4], row[5], row[6], row[7], row[8]),
        )
        con.commit()
    assert sidecar.wake_state_status().status == "validation_failed"
    sidecar.ensure_schema()
    with sqlite3.connect(sidecar.sidecar_db_path) as con:
        assert con.execute("SELECT COUNT(*) FROM wake_state_snapshots WHERE active=1").fetchone()[0] == 1
        assert con.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='index' AND name='uq_wake_state_single_active'").fetchone()[0] == 1


def test_invalid_source_run_id_is_reported(tmp_path: Path) -> None:
    sidecar = _sidecar(tmp_path)
    assert sidecar.prepare().status == "ready"
    with sqlite3.connect(sidecar.sidecar_db_path) as con:
        con.execute("PRAGMA foreign_keys=OFF")
        con.execute("UPDATE wake_state_snapshots SET source_run_id='missing-run' WHERE active=1")
        con.commit()
    assert sidecar.wake_state_status().status == "source_run_invalid"


def test_source_foreign_key_error_blocks_all_writes(tmp_path: Path) -> None:
    sidecar = _sidecar(tmp_path, bad_fk=True)
    report = sidecar.prepare()
    assert report.status == "validation_failed"
    assert not sidecar.sidecar_db_path.exists()


def test_unreadable_sqlite_reports_validation_failure(tmp_path: Path) -> None:
    source = tmp_path / "source.sqlite3"
    source.write_bytes(b"not a sqlite database")
    sidecar = MemoryNormalizationSidecar(
        tmp_path, source_db_path=source, sidecar_db_path=tmp_path / "audit.sqlite3", runtime_version="v15.0.3.2"
    )
    report = sidecar.prepare()
    assert report.status == "validation_failed"
    assert not sidecar.sidecar_db_path.exists()


def test_dry_run_does_not_create_sidecar(tmp_path: Path) -> None:
    sidecar = _sidecar(tmp_path)
    report = sidecar.prepare(dry_run=True)
    assert report.dry_run is True
    assert report.normalization_performed is False
    assert not sidecar.sidecar_db_path.exists()


def test_sidecar_foreign_key_error_fails_deep_verify(tmp_path: Path) -> None:
    sidecar = _sidecar(tmp_path)
    assert sidecar.prepare().status == "ready"
    with sqlite3.connect(sidecar.sidecar_db_path) as con:
        con.execute("PRAGMA foreign_keys=OFF")
        con.execute("UPDATE normalized_memory_items SET speaker_actor_id='missing-actor'")
        con.commit()
    assert sidecar.wake_state_status(deep_verify=True).status == "validation_failed"


def test_large_source_produces_bounded_snapshot(tmp_path: Path) -> None:
    sidecar = _sidecar(tmp_path, count=5000)
    report = sidecar.prepare()
    assert report.status == "ready"
    with sqlite3.connect(sidecar.sidecar_db_path) as con:
        raw, = con.execute("SELECT snapshot_json FROM wake_state_snapshots WHERE active=1").fetchone()
    snapshot = json.loads(raw)
    assert snapshot["source_counts"]["normalized_memory_items"] == 5000
    assert len(snapshot["recent_events"]) <= 12
    assert len(raw.encode("utf-8")) < 100_000


def test_fast_status_observes_active_wal_without_writing(tmp_path: Path) -> None:
    sidecar = _sidecar(tmp_path)
    assert sidecar.prepare().status == "ready"
    writer = sqlite3.connect(sidecar.sidecar_db_path)
    try:
        writer.execute("PRAGMA journal_mode=WAL")
        writer.execute("CREATE TABLE IF NOT EXISTS wal_visibility_probe(value TEXT)")
        writer.execute("INSERT INTO wal_visibility_probe(value) VALUES('keeps-wal-visible')")
        writer.commit()
        assert sidecar.status().status == "ready"
        assert sidecar.wake_state_status().status == "ready"
    finally:
        writer.close()


def test_technical_metadata_write_keeps_wake_state_ready(tmp_path: Path) -> None:
    sidecar = _sidecar(tmp_path)
    prepared = sidecar.prepare().to_dict()
    snapshot_id = prepared["wake_state"]["active_snapshot"]["snapshot_id"]
    with sqlite3.connect(sidecar.source_db_path) as con:
        con.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('heartbeat','fresh')")
        con.commit()

    status = sidecar.wake_state_status(deep_verify=True).to_dict()
    assert status["status"] == "ready"
    assert status["freshness"]["logical_fingerprint_changed"] is False
    assert status["freshness"]["reason"] in {
        "metadata_only_change", "wal_checkpoint_only", "file_layout_changed_without_logical_change",
    }
    after = sidecar.prepare().to_dict()
    assert after["normalization_performed"] is False
    assert after["snapshot_built"] is False
    assert after["wake_state"]["active_snapshot"]["snapshot_id"] == snapshot_id


def test_wal_and_checkpoint_do_not_invalidate_logical_fingerprint(tmp_path: Path) -> None:
    sidecar = _sidecar(tmp_path)
    prepared = sidecar.prepare().to_dict()
    expected_hash = prepared["normalization"]["source_fingerprint"]["relevant_content_sha256"]
    writer = sqlite3.connect(sidecar.source_db_path)
    try:
        writer.execute("PRAGMA journal_mode=WAL")
        writer.execute("PRAGMA wal_autocheckpoint=0")
        writer.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('daemon_status','started')")
        writer.commit()
        during_wal = sidecar.wake_state_status(deep_verify=True).to_dict()
        assert during_wal["status"] == "ready"
        assert during_wal["freshness"]["current_relevant_content_sha256"] == expected_hash
        writer.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
        after_checkpoint = sidecar.wake_state_status(deep_verify=True).to_dict()
        assert after_checkpoint["status"] == "ready"
        assert after_checkpoint["freshness"]["current_relevant_content_sha256"] == expected_hash
        assert after_checkpoint["freshness"]["reason"] in {
            "wal_checkpoint_only", "file_layout_changed_without_logical_change", "metadata_only_change",
        }
    finally:
        writer.close()


def test_vacuum_layout_change_keeps_wake_state_ready(tmp_path: Path) -> None:
    sidecar = _sidecar(tmp_path)
    prepared = sidecar.prepare().to_dict()
    expected_hash = prepared["normalization"]["source_fingerprint"]["relevant_content_sha256"]
    with sqlite3.connect(sidecar.source_db_path) as con:
        con.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('layout_padding',?)", ("x" * 5000,))
        con.commit()
        con.execute("DELETE FROM meta WHERE key='layout_padding'")
        con.commit()
        con.execute("VACUUM")
    status = sidecar.wake_state_status(deep_verify=True).to_dict()
    assert status["status"] == "ready"
    assert status["freshness"]["current_relevant_content_sha256"] == expected_hash
    assert status["freshness"]["logical_fingerprint_changed"] is False


def test_in_place_semantic_content_change_is_detected_by_deep_verify(tmp_path: Path) -> None:
    sidecar = _sidecar(tmp_path)
    assert sidecar.prepare().status == "ready"
    with sqlite3.connect(sidecar.source_db_path) as con:
        con.execute("UPDATE messages SET content_text='semantically changed' WHERE message_id='m0'")
        con.commit()
    status = sidecar.wake_state_status(deep_verify=True).to_dict()
    assert status["status"] == "source_changed"
    assert status["freshness"]["reason"] == "relevant_content_changed"
    assert status["freshness"]["relevant_content_changed"] is True


def test_relevant_schema_change_invalidates_wake_state(tmp_path: Path) -> None:
    sidecar = _sidecar(tmp_path)
    assert sidecar.prepare().status == "ready"
    with sqlite3.connect(sidecar.source_db_path) as con:
        con.execute("ALTER TABLE messages ADD COLUMN semantic_extension TEXT")
        con.commit()
    status = sidecar.wake_state_status().to_dict()
    assert status["status"] == "source_changed"
    assert status["freshness"]["reason"] == "relevant_schema_changed"
    assert status["freshness"]["relevant_schema_changed"] is True


def test_isolated_daemon_start_status_doctor_stop_preserves_wake_state(tmp_path: Path) -> None:
    runtime_root = tmp_path / "isolated-runtime"
    create_system_smoke_staging(ROOT, runtime_root)
    cfg = JaznConfig(root=runtime_root, allow_network=False, network_time_first=False)
    cfg.memory_db_path_readonly.parent.mkdir(parents=True, exist_ok=True)
    _source(cfg.memory_db_path_readonly)
    initialized = build_runtime_write_access_status(cfg, initialize=True, writes_enabled=True).to_dict()
    assert initialized["ok"] is True
    sidecar = MemoryNormalizationSidecar(
        runtime_root,
        source_db_path=cfg.memory_db_path_readonly,
        sidecar_db_path=cfg.audit_db_path_readonly,
        runtime_version=cfg.version,
    )
    prepared = sidecar.prepare(deep_verify=True).to_dict()
    assert prepared["status"] == "ready"
    assert prepared["wake_state"]["active_snapshot_count"] == 1

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        port = int(probe.getsockname()[1])
    assert port != 8787
    marker = runtime_root / "workspace_runtime" / "isolated" / "JAZN_ACTIVE_RUNTIME.json"
    started = start_daemon(
        cfg, host="127.0.0.1", port=port, marker_output=marker,
        heartbeat_interval=0.2, startup_timeout=20.0,
    )
    assert started["ok"] is True, started
    try:
        current_status = status_payload(
            runtime_root, daemon_host="127.0.0.1", daemon_port=port, marker_output=marker
        )
        current_doctor = doctor_payload(
            runtime_root, daemon_host="127.0.0.1", daemon_port=port, marker_output=marker
        )
        wake = sidecar.wake_state_status(deep_verify=True).to_dict()
        assert current_status["daemon"]["active_state"] in {"active_trusted", "active_degraded"}
        assert current_doctor["ok"] is True
        assert current_doctor["live_evidence"]["endpoint_reachable"] is True
        assert wake["status"] == "ready"
        assert wake["active_snapshot_count"] == 1
        assert wake["active_snapshot"]["validation_status"] == "valid"
        assert wake["freshness"]["logical_fingerprint_changed"] is False
    finally:
        stopped = stop_daemon(
            cfg, host="127.0.0.1", port=port, marker_output=marker, timeout=10.0
        )
        assert stopped["stopped"] is True, stopped


def test_memory_prepare_cli_dry_run_exit_codes_follow_data_status(capsys, tmp_path: Path) -> None:
    missing_code = cli.main([
        "memory-prepare", "--root", str(tmp_path), "--dry-run", "--deep-verify", "--json",
    ])
    missing_payload = json.loads(capsys.readouterr().out)
    assert missing_code == 1
    assert missing_payload["status"] == "source_missing"

    cfg = JaznConfig(root=tmp_path)
    cfg.memory_db_path_readonly.parent.mkdir(parents=True, exist_ok=True)
    _source(cfg.memory_db_path_readonly)
    ok_code = cli.main([
        "memory-prepare", "--root", str(tmp_path), "--dry-run", "--deep-verify", "--json",
    ])
    ok_payload = json.loads(capsys.readouterr().out)
    assert ok_code == 0
    assert ok_payload["status"] == "dry_run_ok"


def test_memory_prepare_cli_validation_failure_is_exit_one(capsys, tmp_path: Path) -> None:
    cfg = JaznConfig(root=tmp_path)
    cfg.memory_db_path_readonly.parent.mkdir(parents=True, exist_ok=True)
    cfg.memory_db_path_readonly.write_bytes(b"not sqlite")
    code = cli.main([
        "memory-prepare", "--root", str(tmp_path), "--dry-run", "--deep-verify", "--json",
    ])
    payload = json.loads(capsys.readouterr().out)
    assert code == 1
    assert payload["status"] == "validation_failed"


def test_memory_prepare_cli_usage_error_is_exit_two() -> None:
    with pytest.raises(SystemExit) as exc:
        cli.main(["memory-prepare", "--unknown-option"])
    assert exc.value.code == 2
