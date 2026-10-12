from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from latka_jazn.config import JaznConfig
from latka_jazn.core.engine import JaznEngine
from latka_jazn.core.engine_construction import EngineRuntimeServices
from latka_jazn.core.runtime_composition import CompositionState, RuntimeCompositionRoot
from latka_jazn.core.procedural_bootstrap import seed_core_procedures


def _files(root: Path) -> dict[str, str]:
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob("*") if p.is_file()}


def test_composition_construction_has_no_io(tmp_path: Path) -> None:
    config = JaznConfig(root=tmp_path / "not-created")
    root = RuntimeCompositionRoot(config)
    assert root.state is CompositionState.NEW
    assert not root.services.ready
    assert _files(tmp_path) == {}
    root.close()
    assert _files(tmp_path) == {}


def test_engine_binding_is_side_effect_free_after_explicit_lifecycle(tmp_path: Path) -> None:
    root = RuntimeCompositionRoot(JaznConfig(root=tmp_path))
    services = root.build()
    assert root.state is CompositionState.BUILT
    assert not services.project_startup_indexer.output_path.exists()
    root.validate()
    root.hydrate()
    root.start()
    assert services.project_startup_indexer.output_path.exists()
    before = _files(tmp_path)
    engine = JaznEngine(services)
    assert _files(tmp_path) == before
    assert engine.store is services.store
    assert engine.event_ledger is services.event_ledger
    engine.shutdown()


def test_engine_refuses_unstarted_dependencies(tmp_path: Path) -> None:
    services = EngineRuntimeServices(JaznConfig(root=tmp_path))
    with pytest.raises(ValueError, match="started RuntimeCompositionRoot"):
        JaznEngine(services)
    assert _files(tmp_path) == {}


def test_lifecycle_rejects_out_of_order_and_duplicate_start(tmp_path: Path) -> None:
    root = RuntimeCompositionRoot(JaznConfig(root=tmp_path))
    with pytest.raises(RuntimeError, match="composition_stage_mismatch"):
        root.start()
    engine = root.create_engine()
    assert root.create_engine() is engine
    with pytest.raises(RuntimeError, match="composition_stage_mismatch"):
        root.start()
    root.close()
    closed = _files(tmp_path)
    root.close()
    assert _files(tmp_path) == closed


def test_partial_build_failure_closes_acquired_stores(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import latka_jazn.core.engine_construction as construction

    closed = []

    class Store:
        def __init__(self, *args, **kwargs):
            pass

        def close(self):
            closed.append("store")

    def fail(*args, **kwargs):
        raise RuntimeError("audit-open-injected")

    monkeypatch.setattr(construction, "MemoryStore", Store)
    monkeypatch.setattr(construction, "AuditContextStore", fail)
    root = RuntimeCompositionRoot(JaznConfig(root=tmp_path))
    with pytest.raises(RuntimeError, match="audit-open-injected"):
        root.build()
    assert root.state is CompositionState.FAILED
    assert closed == ["store"]
    assert not root.services.ready


def test_procedural_seed_identity_survives_release_revision(tmp_path: Path) -> None:
    root = RuntimeCompositionRoot(JaznConfig(root=tmp_path))
    root.build()
    try:
        first = seed_core_procedures(root.services.layered_memory, revision="v109")
        before = _files(tmp_path)
        second = seed_core_procedures(root.services.layered_memory, revision="v110")
        assert first["rule_ids"] == second["rule_ids"]
        assert first["revision"] != second["revision"]
        assert len(first["rule_ids"]) == len(set(first["rule_ids"]))
        for name, digest in before.items():
            if name.endswith("procedural.jsonl"):
                assert _files(tmp_path)[name] == digest
    finally:
        root.close()


def test_dependencies_cannot_bind_two_engines(tmp_path: Path) -> None:
    root = RuntimeCompositionRoot(JaznConfig(root=tmp_path))
    engine = root.create_engine()
    try:
        with pytest.raises(ValueError, match="already bound"):
            JaznEngine(root.services)
    finally:
        root.close()
    engine.shutdown()  # Compatibility close is also idempotent.


def test_seed_preserves_legacy_uuid_and_bytes(tmp_path: Path) -> None:
    root = RuntimeCompositionRoot(JaznConfig(root=tmp_path))
    root.build()
    memory = root.services.layered_memory
    try:
        old = memory.record_procedural_rule(
            trigger="pytanie o tożsamość", action="odpowiadać w pierwszej osobie jako Łatka",
            reason="Łatka to ja, nie opis promptu", priority=100, source="v108",
        )
        seed = seed_core_procedures(memory, revision="v109")
        assert seed["rule_ids"][0] == old.rule_id
        assert seed["inventory"][0]["legacy_identity_preserved"] is True
        assert sum(item["classification"] == "memory_profile_compatibility" for item in seed["inventory"]) == 2
        paths = list(tmp_path.rglob("procedural.jsonl"))
        assert len(paths) == 1
        before = paths[0].read_bytes()
        assert old.rule_id.encode() in before and b'"source": "v108"' in before
        seed_core_procedures(memory, revision="v110")
        assert paths[0].read_bytes() == before
    finally:
        root.close()
