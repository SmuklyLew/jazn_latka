"""F01/F04/F06: dedicated-root storage and canonical recall, no public unlock."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from typing import Any

import pytest

from latka_jazn.config import JaznConfig
from latka_jazn.core.admission_owner_context import public_owner_digest, public_private_context_authorized
from latka_jazn.core.dedicated_private_context import (
    DEDICATED_CONTEXT_ENV, DEDICATED_OWNER_ENV,
)
from latka_jazn.core.engine import JaznEngine
from latka_jazn.core.memory_search_planner import MemorySearchPlanner
from latka_jazn.core.runtime_root import (
    resolve_active_runtime_marker_path, runtime_state_path, workspace_runtime_path,
)
from latka_jazn.memory.availability import build_memory_availability_status, runtime_memory_storage_root
from latka_jazn.memory import living_memory_gateway as gateway_module
from latka_jazn.memory.living_memory_gateway import LivingMemoryGateway
from latka_jazn.memory.memory_recall_contract import MemoryRecallContractBuilder
from latka_jazn.memory.memory_root import memory_path, resolve_memory_root
from latka_jazn.memory.memory_tier_store import MemoryTierStore
from latka_jazn.memory.memory_tiers import (
    MemoryKind, MemoryTruthStatus, ShortTermMemoryPolicy, SourceEvidence,
)
from latka_jazn.memory.runtime_memory_install import resolve_memory_tier_database_path
from latka_jazn.memory.store import MemoryStore


def _prepare(root: Path, subject: str, bind: Any, *, memory: bool = True) -> Path:
    (root / "local_resources").mkdir(parents=True)
    bind(root, subject, None)
    if memory:
        raw = root / "memory" / "raw"
        raw.mkdir(parents=True)
        (raw / "dziennik.json").write_text("[]", encoding="utf-8")
    return root.resolve()


def _select(monkeypatch: pytest.MonkeyPatch, subject: str) -> None:
    # Each selection represents a separately configured process in these
    # deterministic tests; production must not switch tenants in one process.
    for name in ("JAZN_RUNTIME_WORKSPACE_DIR", "JAZN_MEMORY_ROOT",
                 "JAZN_MEMORY_SOURCE_ROOTS", "JAZN_MEMORY_TIER_DB"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("JAZN_MEMORY_MODE", "optional")
    monkeypatch.setenv("JAZN_MEMORY_SYNC_MODE", "off")
    monkeypatch.setenv(DEDICATED_CONTEXT_ENV, "dedicated_root")
    monkeypatch.setenv(DEDICATED_OWNER_ENV, public_owner_digest(subject))


def _seed(root: Path, content: str) -> str:
    config = JaznConfig(root=root)
    store = MemoryStore(config.memory_db_path)
    try:
        store.set_meta("synthetic_owner_canary", content)
    finally:
        store.close()
    policy = ShortTermMemoryPolicy()
    record = policy.create(
        kind=MemoryKind.EPISODIC, content=content, domain="daily_life",
        mode="factual_conversation", truth_status=MemoryTruthStatus.USER_CONFIRMED,
        confidence=0.92, importance=0.89,
        evidence=[SourceEvidence(
            source_type="conversation_segment", source_id="synthetic-source",
            source_sha256=hashlib.sha256(content.encode("utf-8")).hexdigest(),
            conversation_id="same-conversation", node_ids=("same-node",),
            segment_id="same-segment",
            exact_excerpt_sha256=hashlib.sha256(content.encode("utf-8")).hexdigest(),
            timestamp_status="exact",
        )],
        created_at_utc=datetime.now(timezone.utc),
    )
    with MemoryTierStore(resolve_memory_tier_database_path(root)) as tier:
        assert tier.save_record(record).records_written == 1
        assert tier.get_record(record.memory_id) == record
        assert tier.validate()["ok"] is True
    return record.memory_id


def _context(root: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    # Real canonical context method, planner, retrieval and presentation. No
    # model invocation or complete engine lifecycle is simulated as PASS.
    engine = object.__new__(JaznEngine)
    engine.config = JaznConfig(root=root)
    engine.last_user_text = None
    engine.memory_search_planner = MemorySearchPlanner(root)
    engine.living_memory_gateway = LivingMemoryGateway(root)
    def forbidden(*_args: Any, **_kwargs: Any) -> Any:
        pytest.fail("unaudited fallback reader invoked in dedicated context")
    monkeypatch.setattr(engine.memory_search_planner, "search_source_files", forbidden)
    monkeypatch.setattr(engine, "_conversation_archive_context_hits", forbidden)
    return engine._memory_context_for_chatgpt("Co pamiętasz jako pierwsze?", limit=6)


def test_two_dedicated_roots_keep_real_writes_retrieval_and_context_separate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stage05_public_context: Any,
) -> None:
    alice = _prepare(tmp_path / "alice", "alice", stage05_public_context)
    bob = _prepare(tmp_path / "bob", "bob", stage05_public_context)
    a_text = "Syntetyczne wspomnienie Alice — canary-A7P9."
    b_text = "Syntetyczne wspomnienie Bob — canary-B3Q8."
    _select(monkeypatch, "alice")
    a_id = _seed(alice, a_text)
    a_path = resolve_memory_tier_database_path(alice)
    a_write = JaznConfig(root=alice).memory_db_path
    assert a_path.is_relative_to(alice / "memory")
    assert a_write.is_relative_to(alice / "memory")
    assert workspace_runtime_path(alice) == alice / "workspace_runtime"
    with pytest.raises(ValueError, match="dedicated_private_context_owner_unverified"):
        resolve_memory_root(bob)
    _select(monkeypatch, "bob")
    b_id = _seed(bob, b_text)
    b_path = resolve_memory_tier_database_path(bob)
    b_write = JaznConfig(root=bob).memory_db_path
    assert b_path.is_relative_to(bob / "memory")
    assert b_write.is_relative_to(bob / "memory")
    assert not a_path.samefile(b_path) and not a_write.samefile(b_write)
    assert workspace_runtime_path(bob) == bob / "workspace_runtime"
    for root, subject, own_text, foreign_text, own_id, foreign_id in (
        (alice, "alice", a_text, b_text, a_id, b_id),
        (bob, "bob", b_text, a_text, b_id, a_id),
    ):
        _select(monkeypatch, subject)
        store = MemoryStore(JaznConfig(root=root).memory_db_path)
        try:
            assert store.get_meta("synthetic_owner_canary") == own_text
        finally:
            store.close()
        with MemoryTierStore(resolve_memory_tier_database_path(root)) as tier:
            assert tier.get_record(own_id) is not None
            assert tier.get_record(foreign_id) is None
        context = _context(root, monkeypatch)
        assert own_text in repr(context)
        assert foreign_text not in repr(context)
        assert context["retrieval_strategy"]["dedicated_private_context"] == "canonical_gateway_only"
        assert not any(context[k] for k in (
            "episodes", "legacy_messages", "source_file_hits",
            "conversation_archive_hits", "raw_chat_fallback",
        ))
        contract = MemoryRecallContractBuilder().build(context, user_text="synthetic recall")
        assert any(own_text in item["content"] for item in contract.items)
        assert foreign_text not in repr(contract.to_dict())
    # No relaxation of the .26 public owner gate.
    assert public_private_context_authorized(alice, public_owner_digest("alice"))
    assert not public_private_context_authorized(alice, public_owner_digest("bob"))


def test_dedicated_memory_never_adopts_legacy_host_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stage05_public_context: Any,
) -> None:
    root = _prepare(tmp_path / "root", "alice", stage05_public_context, memory=False)
    legacy = root / "workspace_runtime" / "memory" / "raw"
    legacy.mkdir(parents=True)
    (legacy / "dziennik.json").write_text('["foreign legacy"]', encoding="utf-8")
    _select(monkeypatch, "alice")
    assert resolve_memory_root(root) == root / "memory"
    assert not (root / "memory").exists()
    status = build_memory_availability_status(root)
    assert not status.persistent_memory_enabled
    assert runtime_memory_storage_root(root) == root / "workspace_runtime" / "core_state" / "memory_runtime"
    assert not (root / "memory").exists()


@pytest.mark.parametrize("kind", ["workspace", "memory", "marker", "state", "sync"])
def test_dedicated_context_refuses_shared_overrides(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stage05_public_context: Any, kind: str,
) -> None:
    root = _prepare(tmp_path / "root", "alice", stage05_public_context)
    other = tmp_path / "foreign"
    other.mkdir()
    _select(monkeypatch, "alice")
    if kind == "workspace":
        monkeypatch.setenv("JAZN_RUNTIME_WORKSPACE_DIR", str(other))
        with pytest.raises(ValueError, match="workspace_override_not_allowed"):
            workspace_runtime_path(root)
    elif kind == "memory":
        monkeypatch.setenv("JAZN_MEMORY_ROOT", str(other))
        with pytest.raises(ValueError, match="memory_override_not_allowed"):
            resolve_memory_root(root)
    elif kind == "marker":
        with pytest.raises(ValueError, match="marker_override_not_allowed"):
            resolve_active_runtime_marker_path(root, other / "JAZN_ACTIVE_RUNTIME.json")
    elif kind == "state":
        with pytest.raises(ValueError, match="private_context_path_escapes_scope"):
            runtime_state_path(root, other / "runtime_state.json")
    else:
        monkeypatch.setenv("JAZN_MEMORY_SYNC_MODE", "push")
        with pytest.raises(ValueError, match="sync_not_verified"):
            resolve_memory_root(root)
    assert not list(other.iterdir())


def test_gateway_ignores_registry_and_rejects_environment_sources_before_probe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stage05_public_context: Any,
) -> None:
    root = _prepare(tmp_path / "root", "alice", stage05_public_context)
    other = _prepare(tmp_path / "foreign", "bob", stage05_public_context)
    _select(monkeypatch, "bob")
    _seed(other, "Syntetyczny obcy znacznik B8X4.")
    _select(monkeypatch, "alice")
    _seed(root, "Syntetyczny własny znacznik A9Y5.")
    registry = workspace_runtime_path(root) / gateway_module.REGISTRY_FILENAME
    registry.parent.mkdir(parents=True, exist_ok=True)
    registry.write_text(json.dumps({"sources": [{
        "path": str(other), "enabled": True, "read_only": True,
        "trusted": True, "trust_basis": "synthetic-untrusted-registry",
    }]}), encoding="utf-8")
    gateway = LivingMemoryGateway(root)
    plan = MemorySearchPlanner(root).plan("Co pamiętasz jako pierwsze?")
    result = gateway.search(plan)
    assert "A9Y5" in repr(result["hits"]) and "B8X4" not in repr(result)
    assert str(other) not in repr(result["sources"])
    def forbidden(*_args: Any, **_kwargs: Any) -> Any:
        pytest.fail("external source reached database probe")
    monkeypatch.setattr(gateway_module, "probe_unified_memory_database", forbidden)
    monkeypatch.setenv("JAZN_MEMORY_SOURCE_ROOTS", str(other))
    with pytest.raises(ValueError, match="external_sources_not_allowed"):
        gateway.search(plan)


@pytest.mark.parametrize("kind", ["database_hardlink", "wal_hardlink", "directory_symlink"])
def test_dedicated_database_aliases_are_rejected_before_probe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stage05_public_context: Any, kind: str,
) -> None:
    root = _prepare(tmp_path / "root", "alice", stage05_public_context)
    other = tmp_path / "foreign"
    other.mkdir()
    foreign_file = other / "foreign.sqlite3"
    foreign_file.write_bytes(b"synthetic foreign canary")
    _select(monkeypatch, "alice")
    sqlite_dir = root / "memory" / "sqlite"
    try:
        if kind == "directory_symlink":
            sqlite_dir.symlink_to(other, target_is_directory=True)
        else:
            sqlite_dir.mkdir()
            suffix = "-wal" if kind == "wal_hardlink" else ""
            os.link(foreign_file, sqlite_dir / ("memory_jazn.sqlite3" + suffix))
    except OSError as exc:
        pytest.skip(f"filesystem does not permit test link: {type(exc).__name__}")
    def forbidden(*_args: Any, **_kwargs: Any) -> Any:
        pytest.fail("aliased database reached probe")
    monkeypatch.setattr(gateway_module, "probe_unified_memory_database", forbidden)
    with pytest.raises(ValueError, match="private_context_(link|file_alias)_not_allowed"):
        LivingMemoryGateway(root).discover()
    assert foreign_file.read_bytes() == b"synthetic foreign canary"


def test_runtime_writer_rejects_hardlinked_default_shard_before_manifest_creation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stage05_public_context: Any,
) -> None:
    root = _prepare(tmp_path / "root", "alice", stage05_public_context)
    _select(monkeypatch, "alice")
    storage = runtime_memory_storage_root(root, mode="off")
    target = storage / "sqlite" / "runtime_write_v1" / "runtime_memory.sqlite3"
    target.parent.mkdir(parents=True)
    foreign = tmp_path / "foreign.sqlite3"
    foreign.write_bytes(b"foreign writer canary")
    try:
        os.link(foreign, target)
    except OSError as exc:
        pytest.skip(f"filesystem does not permit hardlink: {type(exc).__name__}")
    config = JaznConfig(
        root=root, memory_mode="off",
        memory_db_name="memory/sqlite/runtime_write_v1/runtime_memory.sqlite3",
        conversation_shard_manifest_name="memory/sqlite/runtime_write_v1/runtime_memory_shards.json",
    )
    with pytest.raises(ValueError, match="private_context_file_alias_not_allowed"):
        _ = config.memory_db_path
    assert not (target.parent / "runtime_memory_shards.json").exists()
    assert foreign.read_bytes() == b"foreign writer canary"


def test_dedicated_mode_off_for_memory_never_retrieves_persisted_records(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stage05_public_context: Any,
) -> None:
    root = _prepare(tmp_path / "root", "alice", stage05_public_context)
    _select(monkeypatch, "alice")
    _seed(root, "Syntetyczny znacznik A1Z2.")
    monkeypatch.setenv("JAZN_MEMORY_MODE", "off")
    plan = MemorySearchPlanner(root).plan("Co pamiętasz jako pierwsze?")
    result = LivingMemoryGateway(root).search(plan)
    assert not result["hits"] and not result["memory_search_ready"]
    assert runtime_memory_storage_root(root, mode="off").is_relative_to(root / "workspace_runtime")


def test_dedicated_mode_requires_existing_reviewed_owner_binding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "root"
    (root / "local_resources").mkdir(parents=True)
    _select(monkeypatch, "alice")
    with pytest.raises(ValueError, match="owner_unverified"):
        memory_path(root, "sqlite/memory_jazn.sqlite3")
    assert not (root / "memory").exists()
    assert not (root / ".settings_local").exists()
