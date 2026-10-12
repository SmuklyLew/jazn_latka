from __future__ import annotations

from pathlib import Path

import pytest

from latka_jazn.core.source_origin_ledger import SourceOriginLedger
from latka_jazn.memory import living_memory_gateway as gateway_module
from latka_jazn.memory import runtime_memory_install as install_module
from latka_jazn.memory.living_memory_gateway import LivingMemoryGateway
from latka_jazn.memory.memory_root import (
    default_memory_root,
    legacy_memory_root,
    memory_path,
    resolve_memory_root,
)
from latka_jazn.packaging import memory_package_attach as attach_module


def _runtime_root(tmp_path: Path) -> Path:
    root = tmp_path / "runtime_roots" / "jazn-v1639"
    root.mkdir(parents=True)
    return root


def test_memory_root_defaults_outside_versioned_runtime(tmp_path: Path) -> None:
    root = _runtime_root(tmp_path)
    expected = tmp_path / "workspace_runtime" / "memory"
    assert default_memory_root(root) == expected.resolve()
    assert resolve_memory_root(root) == expected.resolve()
    assert expected.resolve() != legacy_memory_root(root)


def test_memory_root_preserves_existing_legacy_layout_until_attach(tmp_path: Path) -> None:
    root = _runtime_root(tmp_path)
    legacy = legacy_memory_root(root)
    legacy.mkdir(parents=True)
    (legacy / "sentinel.txt").write_text("legacy", encoding="utf-8")

    assert resolve_memory_root(root) == legacy
    assert resolve_memory_root(root, prefer_existing_legacy=False) == default_memory_root(root)


def test_memory_root_relative_override_is_workspace_scoped(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _runtime_root(tmp_path)
    monkeypatch.setenv("JAZN_MEMORY_ROOT", "private-memory")
    expected = tmp_path / "workspace_runtime" / "private-memory"
    assert resolve_memory_root(root) == expected.resolve()
    assert memory_path(root, "memory/sqlite/memory_jazn.sqlite3") == (
        expected / "sqlite" / "memory_jazn.sqlite3"
    ).resolve()


def test_source_origin_ledger_uses_selected_memory_root(tmp_path: Path) -> None:
    root = _runtime_root(tmp_path)
    canonical = default_memory_root(root)
    canonical.mkdir(parents=True)

    ledger = SourceOriginLedger(root)

    assert ledger.path == canonical / "layered" / "source_origin_ledger_current_line.jsonl"
    assert ledger.path.parent.is_dir()


def test_default_transactional_tier_prefers_ready_native_unified(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _runtime_root(tmp_path)
    canonical = memory_path(root, "sqlite/memory_jazn.sqlite3")
    canonical.parent.mkdir(parents=True)
    canonical.touch()

    monkeypatch.setattr(
        install_module,
        "_native_unified_tier_path",
        lambda runtime_root: canonical,
    )
    monkeypatch.delenv("JAZN_MEMORY_TIER_DB", raising=False)

    assert install_module.resolve_memory_tier_database_path(root) == canonical


def test_memory_attach_creates_fresh_host_parent_and_restores_no_legacy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _runtime_root(tmp_path)
    workspace = tmp_path / "workspace_runtime"
    source = tmp_path / "staging" / "memory"
    source.mkdir(parents=True)
    (source / "MEMORY_PACKAGE_MANIFEST.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        attach_module,
        "initialize_transactional_memory_store",
        lambda runtime_root: {"ok": True, "database_path": "test"},
    )

    backup, had_previous = attach_module._install_memory_tree(root, workspace, source, {})

    target = default_memory_root(root)
    assert had_previous is False
    assert not backup.exists()
    assert (target / "MEMORY_PACKAGE_MANIFEST.json").is_file()


def test_memory_attach_moves_existing_legacy_memory_to_backup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _runtime_root(tmp_path)
    workspace = tmp_path / "workspace_runtime"
    legacy = legacy_memory_root(root)
    legacy.mkdir(parents=True)
    (legacy / "old.txt").write_text("old", encoding="utf-8")
    source = tmp_path / "staging" / "memory"
    source.mkdir(parents=True)
    (source / "new.txt").write_text("new", encoding="utf-8")
    monkeypatch.setattr(
        attach_module,
        "initialize_transactional_memory_store",
        lambda runtime_root: {"ok": True, "database_path": "test"},
    )

    backup, had_previous = attach_module._install_memory_tree(root, workspace, source, {})

    assert had_previous is True
    assert (backup / "old.txt").read_text(encoding="utf-8") == "old"
    assert not legacy.exists()
    assert (default_memory_root(root) / "new.txt").read_text(encoding="utf-8") == "new"


def test_gateway_deduplicates_native_unified_and_transactional_same_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _runtime_root(tmp_path)
    memory_root = default_memory_root(root)
    canonical = memory_root / "sqlite" / "memory_jazn.sqlite3"
    canonical.parent.mkdir(parents=True)
    canonical.touch()

    monkeypatch.setattr(gateway_module, "resolve_memory_root", lambda runtime_root: memory_root)
    monkeypatch.setattr(
        gateway_module,
        "probe_unified_memory_database",
        lambda path, **kwargs: {
            "status": "ready_native_unified",
            "memory_search_ready": True,
        },
    )
    monkeypatch.setattr(
        gateway_module,
        "resolve_memory_tier_database_path",
        lambda runtime_root: canonical,
    )
    monkeypatch.setattr(
        gateway_module,
        "probe_memory_tier_database_readonly",
        lambda path, **kwargs: {
            "status": "ready",
            "memory_search_ready": True,
        },
    )

    gateway = LivingMemoryGateway(root, discovery_cache_seconds=0)
    sources = gateway.discover()
    native = [item for item in sources if item.get("source_kind") == "native_unified"]
    separate_tier = [
        item for item in sources if item.get("source_kind") == "transactional_tier_memory"
    ]

    assert len(native) == 1
    assert separate_tier == []
    assert native[0]["transactional_tier_same_database"] is True
    assert native[0]["selected_transactional_tier"] is True
    readiness = gateway.readiness()
    assert readiness["status"] == "ready_native_unified_transactional_single_database"
    assert readiness["selected_source_count"] == 1
    assert readiness["transactional_tier_search_ready"] is True
