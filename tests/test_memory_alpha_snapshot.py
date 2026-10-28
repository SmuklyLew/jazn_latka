from __future__ import annotations

from contextlib import closing
import json
import shutil
import sqlite3
from pathlib import Path

import pytest

from latka_jazn.cli import build_parser
from latka_jazn.tools.memory_alpha_snapshot import (
    AlphaSnapshotError,
    EVIDENCE,
    create_snapshot,
    verify_snapshot,
)


def _source(tmp_path: Path, *, wal: bool = False) -> tuple[Path, sqlite3.Connection]:
    root = tmp_path / "memory"
    database = root / "sqlite" / "runtime_write_v1" / "runtime_memory.sqlite3"
    database.parent.mkdir(parents=True)
    conn = sqlite3.connect(database)
    if wal:
        conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("CREATE TABLE entries(id INTEGER PRIMARY KEY, content TEXT)")
    conn.execute("INSERT INTO entries(content) VALUES ('committed memory')")
    conn.commit()
    (root / "raw").mkdir()
    (root / "raw" / "dziennik.json").write_text('{"memory": true}', encoding="utf-8")
    return root, conn


def test_operator_confirmation_required_before_any_write(tmp_path: Path) -> None:
    source, connection = _source(tmp_path)
    try:
        target = tmp_path / "snapshot"
        with pytest.raises(AlphaSnapshotError, match="WRITERS_PAUSED"):
            create_snapshot(source, target, writer_confirmation="", emit=lambda _: None)
        assert not target.exists()
    finally:
        connection.close()


def test_sqlite_wal_and_raw_round_trip_without_promotion(tmp_path: Path) -> None:
    source, connection = _source(tmp_path, wal=True)
    try:
        target = tmp_path / "snapshot"
        events: list[str] = []
        result = create_snapshot(
            source, target, writer_confirmation="WRITERS_PAUSED",
            emit=events.append,
        )
        assert result["ok"] is True
        assert result["sqlite_passed"] == 1
        assert result["cross_database_atomicity_proven"] is False
        assert result["application_restore_tested"] is False
        assert target.is_dir()
        assert events and any("[DONE]" in event for event in events)
        evidence = json.loads((target / EVIDENCE).read_text(encoding="utf-8"))
        assert evidence["writer_quiescence_evidence"] == "operator_attested_only"
        assert any(e["method"] == "sqlite_online_backup_api" for e in evidence["files"])
        assert not list(target.rglob("*-wal"))
        assert not list(target.rglob("*-shm"))
        db = target / "sqlite" / "runtime_write_v1" / "runtime_memory.sqlite3"
        with closing(sqlite3.connect(db)) as restored:
            assert restored.execute("SELECT content FROM entries").fetchone()[0] == "committed memory"
        assert verify_snapshot(target, emit=lambda _: None)["ok"] is True
        assert (source / "raw" / "dziennik.json").is_file()
    finally:
        connection.close()


def test_tamper_is_detected(tmp_path: Path) -> None:
    source, connection = _source(tmp_path)
    connection.close()
    target = tmp_path / "snapshot"
    create_snapshot(source, target, writer_confirmation="WRITERS_PAUSED", emit=lambda _: None)
    (target / "raw" / "dziennik.json").write_text('{"tampered":true}', encoding="utf-8")
    with pytest.raises(AlphaSnapshotError, match="mismatch"):
        verify_snapshot(target, emit=lambda _: None)


def test_existing_destination_is_never_replaced(tmp_path: Path) -> None:
    source, connection = _source(tmp_path)
    connection.close()
    target = tmp_path / "snapshot"
    target.mkdir()
    marker = target / "keep.txt"
    marker.write_text("protected", encoding="utf-8")
    with pytest.raises(AlphaSnapshotError, match="already exists"):
        create_snapshot(source, target, writer_confirmation="WRITERS_PAUSED", emit=lambda _: None)
    assert marker.read_text(encoding="utf-8") == "protected"


def test_source_target_overlap_is_rejected(tmp_path: Path) -> None:
    source, connection = _source(tmp_path)
    connection.close()
    with pytest.raises(AlphaSnapshotError, match="overlap"):
        create_snapshot(
            source, source / "nested", writer_confirmation="WRITERS_PAUSED",
            emit=lambda _: None,
        )


def test_isolated_clone_can_be_verified_without_runtime_start(tmp_path: Path) -> None:
    source, connection = _source(tmp_path)
    connection.close()
    target = tmp_path / "snapshot"
    create_snapshot(source, target, writer_confirmation="WRITERS_PAUSED", emit=lambda _: None)
    drill = tmp_path / "isolated-restore-drill"
    shutil.copytree(target, drill)
    assert verify_snapshot(drill, emit=lambda _: None)["sqlite_passed"] == 1
    assert not (tmp_path / "daemon.pid").exists()


def test_cli_exposes_canonical_alpha_snapshot_command() -> None:
    args = build_parser().parse_args([
        "memory-alpha-snapshot", "--mode", "verify",
        "--destination", "/tmp/alpha-snapshot", "--json",
    ])
    assert args.command == "memory-alpha-snapshot"
    assert args.mode == "verify"
    assert args.as_json is True


def test_active_shard_size_rebased_only_in_staging(tmp_path: Path) -> None:
    source, connection = _source(tmp_path, wal=True)
    try:
        manifest = source / "sqlite" / "runtime_write_v1" / "runtime_memory_shards.json"
        manifest.write_text(json.dumps({
            "active_write_shard": "0001",
            "shards": [{
                "shard_id": "0001", "role": "active_write",
                "path": "sqlite/runtime_write_v1/runtime_memory.sqlite3",
                "size_bytes": 0,
            }]
        }), encoding="utf-8")
        original = manifest.read_bytes()
        target = tmp_path / "snapshot"
        result = create_snapshot(source, target, writer_confirmation="WRITERS_PAUSED", emit=lambda _: None)
        assert result["ok"] is True
        assert manifest.read_bytes() == original
        staged_manifest = json.loads(
            (target / "sqlite" / "runtime_write_v1" / "runtime_memory_shards.json").read_text()
        )
        staged_size = (
            target / "sqlite" / "runtime_write_v1" / "runtime_memory.sqlite3"
        ).stat().st_size
        assert staged_manifest["shards"][0]["size_bytes"] == staged_size
        evidence = json.loads((target / EVIDENCE).read_text(encoding="utf-8"))
        assert evidence["normalized_active_shards"]
        assert verify_snapshot(target, emit=lambda _: None)["ok"] is True
    finally:
        connection.close()


def test_invalid_sealed_shard_never_promoted(tmp_path: Path) -> None:
    source, connection = _source(tmp_path)
    connection.close()
    manifest = source / "sqlite" / "runtime_write_v1" / "runtime_memory_shards.json"
    manifest.write_text(json.dumps({
        "active_write_shard": "0002",
        "shards": [
            {"shard_id": "0001", "role": "sealed",
             "path": "sqlite/runtime_write_v1/runtime_memory.sqlite3",
             "size_bytes": 1, "sha256": "0" * 64},
            {"shard_id": "0002", "role": "active_write",
             "path": "sqlite/runtime_write_v1/runtime_memory.sqlite3",
             "size_bytes": 1}
        ],
    }), encoding="utf-8")
    target = tmp_path / "snapshot"
    with pytest.raises(AlphaSnapshotError, match="shard SHA256 mismatch"):
        create_snapshot(source, target, writer_confirmation="WRITERS_PAUSED", emit=lambda _: None)
    assert not target.exists()


def test_verify_shard_metadata_inconsistent_fails_closed(tmp_path: Path) -> None:
    source, connection = _source(tmp_path)
    connection.close()
    target = tmp_path / "snapshot"
    create_snapshot(source, target, writer_confirmation="WRITERS_PAUSED", emit=lambda _: None)
    manifest = target / "sqlite" / "runtime_write_v1" / "runtime_memory_shards.json"
    manifest.write_text(json.dumps({
        "active_write_shard": "9999", "shards": [
            {"shard_id": "0002", "role": "active_write",
             "path": "sqlite/runtime_write_v1/runtime_memory.sqlite3",
             "size_bytes": 0}
        ]
    }), encoding="utf-8")
    with pytest.raises(AlphaSnapshotError):
        verify_snapshot(target, emit=lambda _: None)
