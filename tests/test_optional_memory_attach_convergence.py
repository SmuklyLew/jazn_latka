from __future__ import annotations

import json
from pathlib import Path

import pytest

from latka_jazn.config import JaznConfig
from latka_jazn.memory.availability import (
    build_memory_availability_status,
    runtime_memory_storage_root,
)
from latka_jazn.memory.layered_memory import LayeredMemory
from latka_jazn.memory.living_memory_gateway import LivingMemoryGateway
from latka_jazn.memory.runtime_memory_install import initialize_transactional_memory_store
from latka_jazn.memory.runtime_persistence import RuntimeMemoryWriter
from latka_jazn.memory.runtime_write_access_contract import build_runtime_write_access_status
from latka_jazn.memory.store import MemoryStore
from tools.jazn_pack_generator_app.constants import SYSTEM_BOOTSTRAP_REQUIRED_FILES
from tools.jazn_pack_generator_app.manifest import build_memory_attachment_contract
from tools.jazn_pack_generator_app.models import ContentMode, PackPlan, PackRequest, SourceEntry


def _runtime_root(tmp_path: Path) -> Path:
    root = tmp_path / "runtime"
    root.mkdir()
    return root


def _is_under(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def _pack_plan(tmp_path: Path, content: ContentMode) -> PackPlan:
    source_root = tmp_path / "source"
    source_root.mkdir(exist_ok=True)
    if content == ContentMode.MEMORY:
        names = ("memory/example.json",)
    else:
        names = tuple(SYSTEM_BOOTSTRAP_REQUIRED_FILES)
    entries = tuple(
        SourceEntry(
            source=source_root / name,
            archive_path=name,
            size_bytes=1,
            is_dir=False,
        )
        for name in names
    )
    return PackPlan(
        request=PackRequest(
            source_root=source_root,
            output_root=tmp_path / "out",
            content=content,
        ),
        package_version="16.3.25.5.74.2.002-test",
        package_basename="test.zip",
        entries=entries,
        excluded=(),
        source_total_size_bytes=len(entries),
    )


def test_system_only_runtime_uses_core_state_without_materializing_private_memory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _runtime_root(tmp_path)
    workspace = tmp_path / "host-workspace"
    monkeypatch.setenv("JAZN_RUNTIME_WORKSPACE_DIR", str(workspace))
    monkeypatch.delenv("JAZN_MEMORY_ROOT", raising=False)
    monkeypatch.setenv("JAZN_MEMORY_MODE", "optional")

    before = build_memory_availability_status(root)
    assert before.status == "persistent_memory_absent_optional"
    assert before.core_runtime_allowed is True
    assert before.ordinary_dialogue_allowed is True
    assert before.persistent_memory_enabled is False

    cfg = JaznConfig(root=root)
    runtime_write = build_runtime_write_access_status(
        cfg,
        initialize=True,
        writes_enabled=True,
    )

    assert runtime_write.ok is True
    assert runtime_write.initialized is True
    assert cfg.memory_availability.persistent_memory_enabled is False
    assert not cfg.memory_root.exists()
    assert _is_under(cfg.memory_db_path_readonly, workspace / "core_state" / "memory_runtime")
    assert _is_under(cfg.audit_db_path_readonly, workspace / "core_state" / "memory_runtime")


def test_transactional_memory_is_skipped_when_memory_is_optional_and_absent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _runtime_root(tmp_path)
    workspace = tmp_path / "workspace"
    monkeypatch.setenv("JAZN_RUNTIME_WORKSPACE_DIR", str(workspace))
    monkeypatch.setenv("JAZN_MEMORY_MODE", "optional")
    monkeypatch.delenv("JAZN_MEMORY_ROOT", raising=False)

    result = initialize_transactional_memory_store(root)

    assert result["ok"] is True
    assert result["skipped"] is True
    assert result["persistent_memory_enabled"] is False
    assert result["status"] == "persistent_memory_absent_optional"
    assert not (workspace / "memory").exists()


def test_required_memory_mode_is_explicit_fail_closed_policy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _runtime_root(tmp_path)
    monkeypatch.setenv("JAZN_RUNTIME_WORKSPACE_DIR", str(tmp_path / "workspace"))
    monkeypatch.setenv("JAZN_MEMORY_MODE", "required")
    monkeypatch.delenv("JAZN_MEMORY_ROOT", raising=False)

    availability = build_memory_availability_status(root)
    transactional = initialize_transactional_memory_store(root)

    assert availability.status == "persistent_memory_required_missing"
    assert availability.core_runtime_allowed is False
    assert availability.required_satisfied is False
    assert transactional["ok"] is False
    assert transactional["error"] == "persistent_memory_required_missing"


def test_memory_mode_off_ignores_existing_memory_for_runtime_writes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _runtime_root(tmp_path)
    workspace = tmp_path / "workspace"
    memory_root = workspace / "memory"
    (memory_root / "raw").mkdir(parents=True)
    (memory_root / "raw" / "chat.html").write_text("chat", encoding="utf-8")
    monkeypatch.setenv("JAZN_RUNTIME_WORKSPACE_DIR", str(workspace))
    monkeypatch.setenv("JAZN_MEMORY_MODE", "off")

    availability = build_memory_availability_status(root)
    storage = runtime_memory_storage_root(root)

    assert availability.persistent_memory_present is True
    assert availability.persistent_memory_enabled is False
    assert availability.status == "disabled_by_policy"
    assert _is_under(storage, workspace / "core_state")


def test_runtime_writers_do_not_make_core_state_look_like_attached_memory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _runtime_root(tmp_path)
    workspace = tmp_path / "workspace"
    monkeypatch.setenv("JAZN_RUNTIME_WORKSPACE_DIR", str(workspace))
    monkeypatch.setenv("JAZN_MEMORY_MODE", "optional")

    cfg = JaznConfig(root=root)
    store = MemoryStore(cfg.memory_db_path)
    try:
        layered = LayeredMemory(store, root)
        writer = RuntimeMemoryWriter(root, version="test", store=store)
        assert _is_under(layered.memory_root, workspace / "core_state")
        assert _is_under(writer.memory_root, workspace / "core_state")
        assert not (workspace / "memory").exists()
    finally:
        store.close()

    readiness = LivingMemoryGateway(root, discovery_cache_seconds=0).readiness()
    assert readiness["memory_search_ready"] is False
    assert readiness["status"] == "no_ready_memory_source"


def test_existing_external_memory_switches_runtime_storage_back_to_memory_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _runtime_root(tmp_path)
    workspace = tmp_path / "workspace"
    memory_root = workspace / "memory"
    (memory_root / "raw").mkdir(parents=True)
    (memory_root / "raw" / "chat.html").write_text("chat", encoding="utf-8")
    monkeypatch.setenv("JAZN_RUNTIME_WORKSPACE_DIR", str(workspace))
    monkeypatch.setenv("JAZN_MEMORY_MODE", "optional")

    availability = build_memory_availability_status(root)
    storage = runtime_memory_storage_root(root)

    assert availability.status == "persistent_memory_present"
    assert availability.persistent_memory_enabled is True
    assert storage == memory_root.resolve()


def test_generator_declares_system_memory_as_optional_and_attachable(tmp_path: Path) -> None:
    system = build_memory_attachment_contract(_pack_plan(tmp_path, ContentMode.SYSTEM))
    assert system["system_present"] is True
    assert system["memory_present_in_this_package"] is False
    assert system["persistent_memory_required_for_core_runtime"] is False
    assert system["ordinary_dialogue_without_persistent_memory"] is True
    assert system["recall_without_verified_persistent_memory"] is False
    assert system["external_memory_attach_supported"] is True
    assert system["canonical_memory_root"] == "workspace_runtime/memory"
    assert system["operational_core_state_root"] == "workspace_runtime/core_state"
    assert system["bootstrap_contract_member"] == "MEMORY_ATTACHMENT_CONTRACT.json"
    assert "MEMORY_ATTACHMENT_CONTRACT.json" in SYSTEM_BOOTSTRAP_REQUIRED_FILES


def test_generator_declares_memory_package_data_only(tmp_path: Path) -> None:
    memory = build_memory_attachment_contract(_pack_plan(tmp_path, ContentMode.MEMORY))
    assert memory["system_present"] is False
    assert memory["memory_present_in_this_package"] is True
    assert memory["external_memory_attach_supported"] is False
    assert memory["memory_package_is_active_root"] is False


def test_root_memory_attachment_contract_matches_runtime_policy() -> None:
    root = Path(__file__).resolve().parents[1]
    payload = json.loads((root / "MEMORY_ATTACHMENT_CONTRACT.json").read_text(encoding="utf-8"))
    assert payload["schema_version"] == "jazn_memory_attachment_contract/v1"
    assert payload["persistent_memory_required_for_core_runtime"] is False
    assert payload["ordinary_dialogue_without_persistent_memory"] is True
    assert payload["recall_without_verified_persistent_memory"] is False
    assert payload["canonical_memory_root"] == "workspace_runtime/memory"
    assert payload["operational_core_state_root"] == "workspace_runtime/core_state"
