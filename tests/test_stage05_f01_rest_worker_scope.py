"""Stage05 dedicated-root replay and actual spawned worker regression gates."""
from __future__ import annotations

from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
from types import SimpleNamespace
from typing import Any

import pytest

from latka_jazn.config import JaznConfig
from latka_jazn.core.admission_owner_context import public_owner_digest, public_private_context_authorized
from latka_jazn.core.dedicated_private_context import DEDICATED_CONTEXT_ENV, DEDICATED_OWNER_ENV
from latka_jazn.core.engine_construction import EngineRuntimeServices, resolve_operational_lessons_path
from latka_jazn.core.rest_cycle_controller import RestCycleController
from latka_jazn.core.turn_execution import TurnExecutionContext
from latka_jazn.core.turn_timeout import (
    HardIsolatedRuntimeSessionWorker, RuntimeWorkerProcessError,
    _verify_worker_private_scope, _worker_private_scope,
)
from latka_jazn.memory.memory_tier_store import MemoryTierStore
from latka_jazn.memory.memory_tiers import MemoryKind, MemoryTruthStatus, ShortTermMemoryPolicy, SourceEvidence
from latka_jazn.memory.rest_cycle_store import RestCycleStore
from latka_jazn.memory.rest_replay import RestReplayEngine


def _prepare(root: Path, subject: str, bind: Any) -> Path:
    (root / "local_resources").mkdir(parents=True)
    bind(root, subject, None)
    raw = root / "memory" / "raw"
    raw.mkdir(parents=True)
    (raw / "dziennik.json").write_text("[]", encoding="utf-8")
    return root.resolve()


def _select(monkeypatch: pytest.MonkeyPatch, subject: str) -> None:
    for name in ("JAZN_RUNTIME_WORKSPACE_DIR", "JAZN_MEMORY_ROOT",
                 "JAZN_MEMORY_SOURCE_ROOTS", "JAZN_MEMORY_TIER_DB",
                 "JAZN_REST_CYCLE_DB", "JAZN_NORMALIZATION_SIDECAR_DB"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv(DEDICATED_CONTEXT_ENV, "dedicated_root")
    monkeypatch.setenv(DEDICATED_OWNER_ENV, public_owner_digest(subject))
    monkeypatch.setenv("JAZN_MEMORY_SYNC_MODE", "off")


def _seed(config: JaznConfig, label: str) -> None:
    record = ShortTermMemoryPolicy().create(
        kind=MemoryKind.REFLECTION, content=label, domain="synthetic", mode="test",
        truth_status=MemoryTruthStatus.USER_CONFIRMED, confidence=0.9, importance=0.9,
        evidence=(SourceEvidence(source_type="test", source_id="same-source"),),
    )
    with MemoryTierStore(config.memory_tier_db_path) as store:
        store.save_record(record)
        with store.transaction():
            store.con.execute(
                "UPDATE memory_store_meta SET value='read-must-not-rewrite' WHERE key='truth_boundary'"
            )


def _sentinel(config: JaznConfig) -> str:
    with closing(sqlite3.connect(config.memory_tier_db_path)) as con:
        return str(con.execute("SELECT value FROM memory_store_meta WHERE key='truth_boundary'").fetchone()[0])


class _ReplayProbeSession:
    """Picklable test session: executes real storage/replay in the spawned child."""
    def __init__(self, config: JaznConfig, *, session_id: str | None,
                 no_carryover: bool, source_client: str) -> None:
        self.config = config
        self.state = SimpleNamespace(session_id=session_id)

    def process_user_text(self, user_text: str, **_kwargs: Any) -> dict[str, Any]:
        return {"replay": [item.content for item in RestReplayEngine(self.config).select()]}

    def close(self) -> None:
        pass


def _spawn(config: JaznConfig) -> HardIsolatedRuntimeSessionWorker:
    return HardIsolatedRuntimeSessionWorker(
        session_factory=_ReplayProbeSession, config=config, session_id="same-session",
        no_carryover=False, source_client="synthetic", command="chat",
        startup_timeout_seconds=45, timeout_seconds=30,
    )


def test_two_spawned_workers_reopen_only_their_own_persisted_replay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stage05_public_context: Any,
) -> None:
    alice = _prepare(tmp_path / "alice#50%", "alice", stage05_public_context)
    bob = _prepare(tmp_path / "bob%20", "bob", stage05_public_context)
    for root, subject, label in ((alice, "alice", "alice-canary-A"), (bob, "bob", "bob-canary-B")):
        _select(monkeypatch, subject)
        config = JaznConfig(root=root, memory_mode="optional")
        _seed(config, label)
    for root, subject, own, foreign in (
        (alice, "alice", "alice-canary-A", "bob-canary-B"),
        (bob, "bob", "bob-canary-B", "alice-canary-A"),
        (alice, "alice", "alice-canary-A", "bob-canary-B"),
    ):
        _select(monkeypatch, subject)
        config = JaznConfig(root=root, memory_mode="optional")
        worker = _spawn(config)
        try:
            context = TurnExecutionContext.create(
                session_id="same-session", timeout_seconds=30,
            )
            result = worker.process_user_text("synthetic replay", _turn_context=context)
            assert result["replay"] == [own]
            assert foreign not in repr(result)
            assert result["hard_worker_process"]["worker_pid"] != os.getpid()
            assert _sentinel(config) == "read-must-not-rewrite"
            monkeypatch.setenv(DEDICATED_CONTEXT_ENV, "off")
            with pytest.raises(RuntimeWorkerProcessError) as exc:
                worker.process_user_text("must not dispatch", _turn_context=context)
            assert exc.value.error_code == "runtime_worker_private_scope_unverified"
            monkeypatch.setenv(DEDICATED_CONTEXT_ENV, "dedicated_root")
        finally:
            worker.close()
    assert public_private_context_authorized(alice, public_owner_digest("alice"))
    assert not public_private_context_authorized(alice, public_owner_digest("bob"))


@pytest.mark.parametrize("kind", ["owner", "off", "external", "audit", "memory_mode"])
def test_worker_scope_rejects_mismatched_environment_and_audit_before_use(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stage05_public_context: Any, kind: str,
) -> None:
    root = _prepare(tmp_path / "alice", "alice", stage05_public_context)
    _select(monkeypatch, "alice")
    config = JaznConfig(root=root, memory_mode="optional")
    scope = _worker_private_scope(config)
    assert scope is not None
    _verify_worker_private_scope(config, scope)
    foreign = tmp_path / "foreign.sqlite3"
    audit = None
    if kind == "owner":
        monkeypatch.setenv(DEDICATED_OWNER_ENV, public_owner_digest("bob"))
    elif kind == "off":
        monkeypatch.setenv(DEDICATED_CONTEXT_ENV, "off")
    elif kind == "external":
        monkeypatch.setenv("JAZN_MEMORY_SOURCE_ROOTS", str(tmp_path))
    elif kind == "audit":
        audit = foreign
    else:
        config.memory_mode = "off"
    with pytest.raises(ValueError, match="(dedicated_|private_context_)"):
        _verify_worker_private_scope(config, scope, audit_db_path=audit)
    assert not foreign.exists()


def test_dedicated_replay_off_and_foreign_paths_are_not_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stage05_public_context: Any,
) -> None:
    root = _prepare(tmp_path / "alice", "alice", stage05_public_context)
    _select(monkeypatch, "alice")
    config = JaznConfig(root=root, memory_mode="optional")
    _seed(config, "private-canary")
    reader = RestReplayEngine(config)
    assert [item.content for item in reader.select()] == ["private-canary"]
    reader.tier_path = tmp_path / "foreign.sqlite3"
    with pytest.raises(ValueError, match="dedicated_rest_replay_path_mismatch"):
        reader.select()
    disabled = RestReplayEngine(JaznConfig(root=root, memory_mode="off"))
    def forbidden(**_kwargs: Any) -> Any:
        pytest.fail("disabled replay attempted persistent memory access")
    monkeypatch.setattr(disabled, "_normalized_candidates", forbidden)
    monkeypatch.setattr(disabled, "_tier_candidates", forbidden)
    assert disabled.select() == []
    assert _sentinel(config) == "read-must-not-rewrite"
    assert not reader.tier_path.exists()


def test_rest_refuses_foreign_store_and_persists_only_local_bookkeeping(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stage05_public_context: Any,
) -> None:
    root = _prepare(tmp_path / "alice", "alice", stage05_public_context)
    _select(monkeypatch, "alice")
    config = JaznConfig(root=root, memory_mode="off", rest_cycle_enabled=True)
    foreign_path = tmp_path / "foreign.sqlite3"
    with RestCycleStore(foreign_path) as foreign:
        with pytest.raises(ValueError, match="dedicated_rest_store_path_mismatch"):
            RestCycleController(config, store=foreign)
        assert foreign.active_episode() is None
    controller = RestCycleController(config)
    try:
        result = controller.tick(force=True)
        assert result is not None and result["status"] == "completed"
        assert result["replay_count"] == 0
        assert controller.store.path == config.rest_cycle_db_path
        assert controller.store.path.is_relative_to(root / "workspace_runtime")
    finally:
        controller.close()
    with RestCycleStore(config.rest_cycle_db_path) as reopened:
        assert reopened.validate()["ok"] is True
    with RestCycleStore(foreign_path) as foreign:
        assert foreign.active_episode() is None


@pytest.mark.parametrize("kind", ["lessons", "lexical_cache", "audit", "recovery"])
def test_dedicated_leaf_aliases_do_not_read_or_modify_foreign_data(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stage05_public_context: Any, kind: str,
) -> None:
    root = _prepare(tmp_path / "alice", "alice", stage05_public_context)
    _select(monkeypatch, "alice")
    config = JaznConfig(root=root, memory_mode="off")
    audit = config.audit_db_path_readonly
    if kind == "lessons":
        target = resolve_operational_lessons_path(root)
    elif kind == "lexical_cache":
        target = config.runtime_workspace_dir / "lexical_intelligence.sqlite3"
    elif kind == "audit":
        target = audit
    else:
        target = audit.parent / "turn_persistence_recovery.jsonl"
    foreign = tmp_path / "foreign-data"
    foreign.write_text(json.dumps({"canary": "foreign"}), encoding="utf-8")
    original = foreign.read_bytes()
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(foreign, target)
    except OSError as exc:
        pytest.skip(f"filesystem does not support hardlink: {type(exc).__name__}")
    if kind in {"lessons", "lexical_cache"}:
        with pytest.raises(ValueError, match="private_context_file_alias_not_allowed"):
            EngineRuntimeServices(config).build_dependencies()
    else:
        context = TurnExecutionContext.create(
            session_id="same-session", timeout_seconds=30, audit_db_path=audit,
        )
        if kind == "audit":
            assert context.persist_audit()["ok"] is False
        else:
            assert context._write_recovery_outbox({"synthetic": True})["written"] is False
    assert foreign.read_bytes() == original
