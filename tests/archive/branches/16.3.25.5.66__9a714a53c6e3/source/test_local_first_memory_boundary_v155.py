from __future__ import annotations

from pathlib import Path

from latka_jazn.config import JaznConfig
from latka_jazn.memory.memory_sync_runtime import MemorySyncRuntime
from latka_jazn.memory.memory_tier_store import MemoryTierStore


def test_default_cloud_sync_is_off_and_status_does_not_create_memory_db(tmp_path, monkeypatch) -> None:
    for name in (
        "JAZN_MEMORY_SYNC_MODE", "JAZN_MEMORY_CLOUD_ENDPOINT", "JAZN_MEMORY_STREAM_ID",
        "JAZN_MEMORY_DEVICE_ID", "JAZN_MEMORY_CLOUD_TOKEN", "JAZN_MEMORY_SYNC_KEY_B64",
    ):
        monkeypatch.delenv(name, raising=False)
    cfg = JaznConfig(root=tmp_path)
    assert cfg.memory_sync_mode == "off"
    db = cfg.memory_tier_db_path
    assert not db.exists()
    status = MemorySyncRuntime(cfg).status(probe_remote=False)
    assert status["configuration"]["enabled"] is False
    assert status["cloud_sync_ready"] is False
    assert status["local_memory_ready_independent_of_cloud"] is True
    assert status["local_replication_state"]["read_only"] is True
    assert not db.exists(), "status must not initialize or migrate the local memory database"


def test_local_memory_store_operates_normally_without_cloud_or_crypto_dependency(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("JAZN_MEMORY_SYNC_MODE", "off")
    monkeypatch.delenv("JAZN_MEMORY_SYNC_KEY_B64", raising=False)
    cfg = JaznConfig(root=tmp_path)
    with MemoryTierStore(cfg.memory_tier_db_path) as store:
        assert store.validate()["ok"] is True
        assert store.stats()["memory_records"] == 0
        assert store.stats()["memory_sync_state"] == 0
    result = MemorySyncRuntime(cfg).sync_once()
    assert result.to_dict() == {
        "push_claimed": 0, "push_accepted": 0, "push_replayed": 0, "push_failed": 0,
        "pull_received": 0, "pull_applied": 0, "pull_conflicts": 0,
        "stale_claims_requeued": 0, "cursor_before": 0, "cursor_after": 0, "error": None,
    }


def test_enabled_sync_requires_complete_operator_configuration_but_does_not_break_status(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("JAZN_MEMORY_SYNC_MODE", "backup")
    monkeypatch.delenv("JAZN_MEMORY_CLOUD_ENDPOINT", raising=False)
    monkeypatch.delenv("JAZN_MEMORY_STREAM_ID", raising=False)
    monkeypatch.delenv("JAZN_MEMORY_DEVICE_ID", raising=False)
    cfg = JaznConfig(root=tmp_path)
    status = MemorySyncRuntime(cfg).status(probe_remote=False)
    assert status["configuration"]["enabled"] is True
    assert set(status["configuration"]["missing_requirements"]) >= {"endpoint", "stream_id", "device_id"}
    assert status["cloud_sync_ready"] is False
