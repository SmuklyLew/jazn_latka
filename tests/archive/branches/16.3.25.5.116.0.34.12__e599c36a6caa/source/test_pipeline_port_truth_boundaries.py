from dataclasses import FrozenInstanceError
from types import SimpleNamespace
from typing import Any
import pytest

from latka_jazn.core.affect_coordinator import AffectProjection
from latka_jazn.core.memory_coordinator import MemoryCoordinator, MemoryProbeRequest
from latka_jazn.core.response_pipeline import ResponsePipeline
from latka_jazn.core.turn_pipeline_state import TurnPipelineState, TurnRequest
from latka_jazn.core.turn_response_policy import TurnResponsePolicy


def test_memory_port_preserves_abstention_and_bound_lineage_without_promotion():
    calls = []
    context = {"gate": "skipped_not_needed", "counts": {}}
    contract = {"items": [], "truth_boundary": "no recall available"}
    diagnostic = {"memory_recall_status": "not_requested"}
    def probe(text, intent, turn_context, client_context, *, turn_id, trace_id):
        calls.append((text, turn_id, trace_id))
        return context, contract, diagnostic
    engine: Any = SimpleNamespace(_build_turn_memory_recall_evidence=probe)
    result = MemoryCoordinator(engine).probe(MemoryProbeRequest(
        "current", SimpleNamespace(primary_intent="ordinary_conversation"), {}, "turn-bound", "trace-bound",
    ))
    assert calls == [("current", "turn-bound", "trace-bound")]
    assert result.context is context and result.recall_contract is contract
    assert result.observability is diagnostic
    assert result.recall_contract["items"] == []


def test_affect_port_is_projection_without_second_durable_authority():
    projection = AffectProjection({"state_emoticon": "test"})
    assert projection.source == "existing_runtime_affect"
    assert projection.advisory and not projection.creates_durable_authority
    with pytest.raises(FrozenInstanceError):
        setattr(projection, "source", "second_owner")


def test_response_plan_keeps_required_and_forbidden_source_constraints():
    state = TurnPipelineState(TurnRequest("current"))
    state.turn_response_policy = TurnResponsePolicy(
        intent="ordinary_conversation", route="ordinary_dialogue", answer_kind="natural_dialogue",
        required_components=["source_boundary"], forbidden_topics=["unsupported_memory_claim"],
    )
    state.route_entry = SimpleNamespace(route="ordinary_dialogue", handler_name="OrdinaryDialogueHandler")
    state.decision_dict = {}
    state.frame = {"memory_recall_contract": {"items": [{"source_id": "selected-evidence-1"}]}}
    pipeline = object.__new__(ResponsePipeline)
    plan = pipeline.build_plan(state)
    assert plan.required_points == ("source_boundary",)
    assert plan.forbidden_claims == ("unsupported_memory_claim",)
    assert plan.evidence_refs == ("selected-evidence-1",)
    assert plan.source_truth_owned_by == "runtime"
    assert not plan.model_may_create_facts and not plan.model_may_commit_memory
