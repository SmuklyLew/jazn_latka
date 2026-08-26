from __future__ import annotations

from pathlib import Path

from latka_jazn.config import JaznConfig
from latka_jazn.memory.memory_root import default_memory_root, legacy_memory_root


def _runtime_root(tmp_path: Path) -> Path:
    root = tmp_path / "runtime_roots" / "jazn-v1639"
    root.mkdir(parents=True)
    return root


def test_config_routes_memory_paths_outside_versioned_runtime(tmp_path: Path) -> None:
    root = _runtime_root(tmp_path)
    config = JaznConfig(root=root)
    memory_root = default_memory_root(root)

    assert config.memory_root == memory_root
    assert config.recovered_memory_db_path.is_relative_to(memory_root)
    assert config.normalization_sidecar_db_path.is_relative_to(memory_root)
    assert config.memory_tier_db_path.is_relative_to(memory_root)
    assert config.rest_cycle_db_path.is_relative_to(memory_root)
    assert config.conversation_archive_manifest_path.is_relative_to(memory_root)
    assert config.conversation_fts_dir.is_relative_to(memory_root)
    assert config.conversation_staging_dir.is_relative_to(memory_root)
    assert config.resolve(config.private_canon_override_path).is_relative_to(memory_root)

    runtime_write = config.runtime_write_db_path
    audit = config.audit_db_path
    assert runtime_write.is_relative_to(memory_root)
    assert audit.is_relative_to(memory_root)
    assert not runtime_write.is_relative_to(root)
    assert not audit.is_relative_to(root)


def test_config_uses_existing_legacy_memory_only_as_compatibility_fallback(tmp_path: Path) -> None:
    root = _runtime_root(tmp_path)
    legacy = legacy_memory_root(root)
    legacy.mkdir(parents=True)
    config = JaznConfig(root=root)

    assert config.memory_root == legacy
    assert config.normalization_sidecar_db_path.is_relative_to(legacy)
