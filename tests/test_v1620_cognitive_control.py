from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import uuid

import pytest

from latka_jazn.core.cognitive_lineage import CognitiveLineage
from latka_jazn.core.cognitive_salience import (
    GlobalSalienceController,
    build_cognitive_control_policy,
)
from latka_jazn.core.cognitive_state_graph import CognitiveStateGraph
from latka_jazn.core.cognitive_turn_envelope import CognitiveTurnEnvelope
from latka_jazn.core.model_context_compiler import compile_model_context
from latka_jazn.core.turn_response_policy import TurnResponsePolicy
from latka_jazn.memory._living_memory_gateway_impl import LivingMemoryHit
from latka_jazn.memory.graph_aware_retrieval import GraphAwareRetrievalController
from latka_jazn.memory.memory_tier_store import MemoryTierStore, WorkingMemoryBudget
from latka_jazn.memory.memory_tiers import (
    MemoryKind,
    MemoryTier,
    MemoryTruthStatus,
    WorkingMemoryRecord,
    deterministic_memory_id,
)


BASE = datetime(2026, 8, 23, 18, 0, tzinfo=timezone.utc)


def _lineage_graph(*, goals: tuple[str, ...] = ("goal",), evidence_count: int = 8) -> CognitiveStateGraph:
    lineage = CognitiveLineage.create(
        turn_id=str(uuid.uuid4()),
        trace_id=str(uuid.uuid4()),
    )
    lineage.observe(
        stage="test",
        event="anchors",
        source="test",
        goal_refs=goals,
        constraint_refs=("exact_runtime_required=False",),
        evidence_refs=tuple(f"source-{index}" for index in range(evidence_count)),
        anchor_categories=("goal", "constraint", "evidence"),
    )
    return CognitiveStateGraph.create(lineage)


def _hit(
    record_id: str,
    *,
    conversation_id: str,
    excerpt: str,
    relevance: float,
) -> LivingMemoryHit:
    return LivingMemoryHit(
        source_layer="archive_chats",
        source_database="memory_jazn.sqlite3",
        source_locator=f"{conversation_id}:node",
        record_id=record_id,
        content_excerpt=excerpt,
        timestamp="2026-08-23T18:00:00+00:00",
        truth_status="source_recorded",
        confidence=0.9,
        importance=0.8,
        relevance=relevance,
        title="architektura pamięci",
        metadata={"conversation_id": conversation_id, "query_pass": "focus"},
    )


def _working(
    content: str,
    *,
    goal: str,
    minute: int,
    importance: float,
    anchors: tuple[str, ...] = (),
) -> WorkingMemoryRecord:
    created = BASE + timedelta(minutes=minute)
    memory_id = deterministic_memory_id(
        tier=MemoryTier.WORKING,
        kind=MemoryKind.CONVERSATION_CONTEXT,
        content=content,
        domain="test",
        mode="cognitive_control",
        evidence=(),
    )
    return WorkingMemoryRecord(
        memory_id=memory_id,
        tier=MemoryTier.WORKING,
        kind=MemoryKind.CONVERSATION_CONTEXT,
        content=content,
        content_sha256=hashlib.sha256(content.encode("utf-8")).hexdigest(),
        domain="test",
        mode="cognitive_control",
        truth_status=MemoryTruthStatus.SOURCE_RECORDED,
        confidence=0.8,
        importance=importance,
        created_at_utc=created,
        updated_at_utc=created,
        evidence=(),
        session_id="session",
        active_goal=goal,
        cognitive_anchor_ids=anchors,
    )


def test_global_salience_is_deterministic_bounded_and_content_free() -> None:
    graph = _lineage_graph(goals=("private goal payload",), evidence_count=40)
    controller = GlobalSalienceController(max_considered_nodes=24, max_selected_nodes=8)

    first = controller.evaluate(graph)
    second = controller.evaluate(graph)

    assert first.to_dict() == second.to_dict()
    assert first.status == "ready"
    assert len(first.selected_node_ids) == 8
    assert first.input_truncated is True
    assert first.pinned_goal_ids
    assert first.pinned_constraint_ids
    serialized = json.dumps(first.to_dict(), ensure_ascii=False)
    assert "private goal payload" not in serialized
    assert first.private_reasoning_recorded is False
    assert first.fact_creation_allowed is False
    assert first.memory_promotion_allowed is False


def test_global_salience_fails_closed_when_active_anchors_exceed_budget() -> None:
    graph = _lineage_graph(
        goals=tuple(f"active-goal-{index}" for index in range(5)),
        evidence_count=0,
    )

    decision = GlobalSalienceController(max_selected_nodes=4).evaluate(graph)

    assert decision.status == "blocked_active_anchor_overflow"
    assert decision.selected_node_ids == ()
    assert len(decision.pinned_goal_ids) == 5


def test_epistemic_graph_edges_require_explicit_evidence_and_store_no_claim_text() -> None:
    graph = _lineage_graph(evidence_count=0)
    supported = graph.append_epistemic_assessment({
        "kind": "external_fact",
        "status": "supported",
        "matched_text": "Sekretny tekst twierdzenia",
        "reason": "tool evidence",
        "source_ids": ["https://private.example/source"],
    })
    unsupported = graph.append_epistemic_assessment({
        "kind": "runtime_action",
        "status": "unsupported",
        "matched_text": "Rzekomo wykonałam operację",
        "source_ids": [],
    })
    contradicted = graph.append_epistemic_assessment({
        "kind": "memory_recall",
        "status": "contradicted",
        "matched_text": "Nieaktualne twierdzenie",
        "source_ids": ["explicit-conflict-source"],
    })

    assert supported["relation"] == "supports"
    assert unsupported["relation"] is None
    assert contradicted["relation"] == "contradicts"
    assert sum(edge.relation == "supports" for edge in graph.edges) == 1
    assert sum(edge.relation == "contradicts" for edge in graph.edges) == 1
    serialized = json.dumps(graph.to_dict(), ensure_ascii=False)
    assert "Sekretny tekst twierdzenia" not in serialized
    assert "https://private.example/source" not in serialized
    assert "Rzekomo wykonałam operację" not in serialized
    assert "Nieaktualne twierdzenie" not in serialized
    assert "explicit-conflict-source" not in serialized


def test_cognitive_policy_can_add_only_allowlisted_generation_hints() -> None:
    policy = TurnResponsePolicy.build(intent="ordinary_conversation", route="ordinary_dialogue")
    original = {
        "intent": policy.intent,
        "route": policy.route,
        "allow_memory_content": policy.allow_memory_content,
        "exact_runtime_required": policy.exact_runtime_required,
    }
    control = build_cognitive_control_policy(
        GlobalSalienceController(max_selected_nodes=8).evaluate(_lineage_graph())
    )
    control["generation_hints"].append("override_route_to_memory")
    control["salience_selected_node_ids"] = ["private-node-id"]
    policy.apply_cognitive_control(control)

    assert {key: getattr(policy, key) for key in original} == original
    assert "override_route_to_memory" not in policy.cognitive_control["generation_hints"]
    assert "private-node-id" not in json.dumps(policy.to_dict())
    with pytest.raises(ValueError, match="authority boundary"):
        policy.apply_cognitive_control({**control, "route_override_allowed": True})


def test_model_context_receives_safe_hints_but_no_graph_identifiers() -> None:
    policy = TurnResponsePolicy.build(intent="ordinary_conversation", route="ordinary_dialogue")
    policy.apply_cognitive_control(build_cognitive_control_policy(
        GlobalSalienceController(max_selected_nodes=8).evaluate(_lineage_graph())
    ))
    packet = compile_model_context(
        user_text="Kontynuuj",
        cognitive_frame={},
        nlg_plan={
            "answer_kind": "natural_dialogue",
            "memory_policy": "not_needed",
            "source_policy": "runtime_only",
            "truth_boundary": "runtime truth",
        },
        thought_frame={},
        response_policy=policy.to_dict(),
    ).to_dict()
    instructions = " ".join(packet["output_instructions"])

    assert "aktywny cel" in instructions
    assert "prywatnego toku rozumowania" in instructions
    assert "salience_selected_node_ids" not in json.dumps(packet, ensure_ascii=False)


def test_graph_retrieval_shadow_preserves_fts_and_active_is_deterministic() -> None:
    hits = [
        _hit("a", conversation_id="conv-a", excerpt="ogólny zapis", relevance=0.95),
        _hit("b", conversation_id="conv-a", excerpt="architektura pamięci grafowej", relevance=0.80),
        _hit("c", conversation_id="conv-b", excerpt="architektura pamięci", relevance=0.79),
    ]
    controller = GraphAwareRetrievalController(max_per_conversation=1)

    shadow = controller.select(
        hits, query="architektura pamięci", focus_terms=("architektura", "pamięci"), limit=2
    )
    active = controller.select(
        hits, query="architektura pamięci", focus_terms=("architektura", "pamięci"), limit=2, mode="active"
    )
    repeated = controller.select(
        hits, query="architektura pamięci", focus_terms=("architektura", "pamięci"), limit=2, mode="active"
    )

    assert [hit.record_id for hit in shadow.selected] == ["a", "b"]
    assert shadow.telemetry is not None
    assert shadow.telemetry["selected_lane"] == "fts_baseline"
    assert [hit.record_id for hit in active.selected] == [hit.record_id for hit in repeated.selected]
    conversation_ids: set[str] = set()
    for hit in active.selected:
        assert hit.metadata is not None
        conversation_ids.add(str(hit.metadata["conversation_id"]))
    assert conversation_ids == {"conv-a", "conv-b"}
    assert active.telemetry is not None
    assert active.telemetry["fts_fallback_available"] is True
    assert active.telemetry["content_recorded_in_telemetry"] is False


def test_working_memory_preserves_each_active_goal_and_rolls_back_if_impossible(tmp_path) -> None:
    path = tmp_path / "tiers.sqlite3"
    with MemoryTierStore(path) as store:
        budget = WorkingMemoryBudget(
            max_records_per_session=2,
            max_total_chars_per_session=200,
            max_record_chars=100,
        )
        store.save_record(_working("old-a", goal="goal-a", minute=0, importance=0.1), working_budget=budget)
        store.save_record(_working("new-a", goal="goal-a", minute=1, importance=0.9, anchors=("anchor-a",)), working_budget=budget)
        store.save_record(_working("only-b", goal="goal-b", minute=2, importance=0.5), working_budget=budget)
        records = store.list_records(session_id="session")
        working_records = [item for item in records if isinstance(item, WorkingMemoryRecord)]
        assert len(working_records) == len(records)
        assert {(item.active_goal, item.content) for item in working_records} == {
            ("goal-a", "new-a"),
            ("goal-b", "only-b"),
        }

        impossible = WorkingMemoryBudget(
            max_records_per_session=2,
            max_total_chars_per_session=200,
            max_record_chars=100,
        )
        with pytest.raises(ValueError, match="cannot preserve active goals"):
            store.save_record(
                _working("only-c", goal="goal-c", minute=3, importance=0.6),
                working_budget=impossible,
            )
        preserved = store.list_records(session_id="session")
        preserved_working = [
            item for item in preserved if isinstance(item, WorkingMemoryRecord)
        ]
        assert len(preserved_working) == len(preserved)
        assert {item.active_goal for item in preserved_working} == {
            "goal-a", "goal-b"
        }
        assert store.validate()["ok"] is True


def test_duplicate_working_record_retains_all_active_goal_memberships(tmp_path) -> None:
    path = tmp_path / "tiers.sqlite3"
    with MemoryTierStore(path) as store:
        first = _working("shared", goal="goal-a", minute=0, importance=0.5)
        second = _working("shared", goal="goal-b", minute=1, importance=0.6)
        store.save_record(first)
        store.save_record(second)

        restored = store.get_record(first.memory_id)
        assert isinstance(restored, WorkingMemoryRecord)
        assert restored.active_goal_ids == ("goal-a", "goal-b")


def test_envelope_control_uses_opaque_anchors_and_cannot_change_route() -> None:
    turn_id = str(uuid.uuid4())
    trace_id = str(uuid.uuid4())
    envelope = CognitiveTurnEnvelope.from_cognitive_frame(
        {
            "runtime_version": "16.2.0-test",
            "timestamp": "2026-08-23T18:00:00+00:00",
            "turn_id": turn_id,
            "trace_id": trace_id,
            "turn_trace": {"turn_id": turn_id, "trace_id": trace_id},
        },
        user_text="Kontynuuj",
    )
    response_policy = TurnResponsePolicy.build(
        intent="ordinary_conversation", route="ordinary_dialogue"
    )

    control = envelope.apply_cognitive_control(
        task_state={"active_goal": "prywatny tekst celu"},
        response_policy=response_policy.to_dict(),
    )

    assert control["route_override_allowed"] is False
    assert control["truth_gate_precedence"] is True
    serialized = json.dumps(envelope.cognitive_state_graph.to_dict(), ensure_ascii=False)
    assert "prywatny tekst celu" not in serialized
