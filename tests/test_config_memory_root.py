from __future__ import annotations

from pathlib import Path

from latka_jazn.config import JaznConfig
from latka_jazn.memory.memory_root import default_memory_root, legacy_memory_root


def _runtime_root(tmp_path: Path) -> Path:
    root = tmp_path / "runtime_roots" / "jazn-v1639"
    root.mkdir(parents=True)
    return root


def test_config_routes_memory_paths_outside_versioned_runtime(tmp_path: Path, monkeypatch) -> None:
    # This test checks the *legacy bare versioned-root* default. The global
    # pytest fixture injects a ROOT-relative acceptance workspace for safety,
    # but that explicit override would mask the fallback being tested here.
    # Removing it affects this test only; the synthetic tmp_path owns both roots.
    monkeypatch.delenv("JAZN_RUNTIME_WORKSPACE_DIR", raising=False)
    root = _runtime_root(tmp_path)
    config = JaznConfig(root=root)
    assert config.runtime_workspace_dir == (tmp_path / "workspace_runtime").resolve()
    memory_root = default_memory_root(root)
    runtime_memory_root = config.runtime_memory_storage_root

    assert config.memory_root == memory_root
    assert runtime_memory_root != memory_root
    assert config.recovered_memory_db_path.is_relative_to(memory_root)
    assert config.normalization_sidecar_db_path.is_relative_to(memory_root)
    assert config.memory_tier_db_path.is_relative_to(memory_root)
    assert config.rest_cycle_db_path.is_relative_to(runtime_memory_root)
    assert config.conversation_archive_manifest_path.is_relative_to(memory_root)
    assert config.conversation_fts_dir.is_relative_to(memory_root)
    assert config.conversation_staging_dir.is_relative_to(memory_root)
    assert config.resolve(config.private_canon_override_path).is_relative_to(memory_root)

    runtime_write = config.runtime_write_db_path
    audit = config.audit_db_path
    assert runtime_write.is_relative_to(runtime_memory_root)
    assert audit.is_relative_to(runtime_memory_root)
    assert not runtime_write.is_relative_to(memory_root)
    assert not audit.is_relative_to(memory_root)
    assert not runtime_write.is_relative_to(root)
    assert not audit.is_relative_to(root)



def test_prepared_runtime_keeps_core_writes_in_own_workspace_without_private_memory(
    tmp_path: Path, monkeypatch,
) -> None:
    # Prepared modern roots must not select a sibling checkout's workspace
    # even without a pytest override; MEMORY remains a separate capability.
    monkeypatch.delenv("JAZN_RUNTIME_WORKSPACE_DIR", raising=False)
    monkeypatch.delenv("JAZN_MEMORY_ROOT", raising=False)
    root = _runtime_root(tmp_path)
    (root / "local_resources").mkdir()
    config = JaznConfig(root=root, memory_mode="off")

    workspace = (root / "workspace_runtime").resolve()
    core_storage = workspace / "core_state" / "memory_runtime"
    assert config.runtime_workspace_dir == workspace
    assert config.runtime_memory_storage_root == core_storage
    assert config.runtime_write_db_path.is_relative_to(core_storage)
    assert config.audit_db_path.is_relative_to(core_storage)
    assert not config.runtime_write_db_path.is_relative_to(config.memory_root)
    assert not config.memory_root.exists()


def test_config_uses_existing_legacy_memory_only_as_compatibility_fallback(tmp_path: Path) -> None:
    root = _runtime_root(tmp_path)
    legacy = legacy_memory_root(root)
    legacy.mkdir(parents=True)
    config = JaznConfig(root=root)

    assert config.memory_root == legacy
    assert config.normalization_sidecar_db_path.is_relative_to(legacy)
