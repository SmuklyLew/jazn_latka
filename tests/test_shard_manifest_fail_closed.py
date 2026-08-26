from __future__ import annotations

from pathlib import Path
import json

import pytest

from latka_jazn.config import JaznConfig
from latka_jazn.db.shard_manifest import ShardManifestError, SQLiteShardManager


def _manifest(*, path: str = "memory/runtime.sqlite3", active: str = "0001") -> dict:
    return {
        "schema_version": "jazn_sqlite_shards/v1",
        "logical_database": "chat_context",
        "role": "canonical_runtime_conversation_memory",
        "active_write_shard": active,
        "max_file_bytes": 1000,
        "shards": [
            {
                "shard_id": "0001",
                "path": path,
                "role": "active_write",
                "created_at_utc": "2026-07-27T00:00:00+00:00",
            }
        ],
    }


def test_missing_manifest_keeps_single_database_compatibility(tmp_path: Path) -> None:
    cfg = JaznConfig(root=tmp_path)
    assert cfg.memory_db_path_readonly == cfg.resolve(cfg.memory_db_name)


def test_existing_invalid_json_is_not_silently_replaced(tmp_path: Path) -> None:
    cfg = JaznConfig(root=tmp_path)
    path = tmp_path / cfg.conversation_shard_manifest_name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{broken", encoding="utf-8")
    with pytest.raises(ShardManifestError, match="cannot read shard manifest"):
        _ = cfg.memory_db_path_readonly
    assert path.read_text(encoding="utf-8") == "{broken"


def test_path_escape_is_rejected_for_read_and_write(tmp_path: Path) -> None:
    cfg = JaznConfig(root=tmp_path)
    path = tmp_path / cfg.conversation_shard_manifest_name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_manifest(path="../outside.sqlite3")), encoding="utf-8")
    with pytest.raises(ShardManifestError, match="unsafe shard path|escapes runtime root"):
        _ = cfg.memory_db_path_readonly
    with pytest.raises(ShardManifestError, match="unsafe shard path|escapes runtime root"):
        _ = cfg.memory_db_path


def test_missing_active_shard_and_duplicate_ids_are_rejected(tmp_path: Path) -> None:
    cfg = JaznConfig(root=tmp_path)
    path = tmp_path / cfg.conversation_shard_manifest_name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_manifest(active="9999")), encoding="utf-8")
    with pytest.raises(ShardManifestError, match="active shard not found exactly once"):
        _ = cfg.memory_db_path_readonly

    duplicate = _manifest()
    duplicate["shards"].append(dict(duplicate["shards"][0]))
    path.write_text(json.dumps(duplicate), encoding="utf-8")
    with pytest.raises(ShardManifestError, match="unique"):
        _ = cfg.memory_db_path_readonly


def test_role_mismatch_is_rejected(tmp_path: Path) -> None:
    cfg = JaznConfig(root=tmp_path)
    path = tmp_path / cfg.conversation_shard_manifest_name
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _manifest()
    payload["role"] = "wrong-role"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ShardManifestError, match="role mismatch"):
        _ = cfg.memory_db_path_readonly


def test_manager_creates_valid_manifest_only_when_missing(tmp_path: Path) -> None:
    manager = SQLiteShardManager(
        tmp_path,
        "memory/shards.json",
        logical_database="chat_context",
        role="canonical_runtime_conversation_memory",
        default_db_path="memory/runtime.sqlite3",
        max_file_bytes=1000,
    )
    manifest = manager.load_or_create()
    assert manifest.active_write_shard == "0001"
    assert manager.manifest_path.is_file()
