from __future__ import annotations

import json
import uuid

from latka_jazn.core.cognitive_lineage import (
    CognitiveLineage,
    constraint_references_from_policy,
    evidence_references_from_memory_contract,
    resolve_parent_thought_id,
)
from latka_jazn.core.cognitive_turn_envelope import CognitiveTurnEnvelope
from latka_jazn.core.turn_route_trace import TurnRouteTrace


def _frame(*, turn_id: str, trace_id: str) -> dict:
    return {
        "schema_version": "chatgpt_cognitive_frame/v1",
        "runtime_version": "v15.4.2.1",
        "timestamp": "🕒 2026-08-14 22:00:00",
        "turn_id": turn_id,
        "trace_id": trace_id,
        "turn_trace": {
            "schema_version": "turn_trace/v1",
            "turn_id": turn_id,
            "trace_id": trace_id,
            "timestamp_header": "🕒 2026-08-14 22:00:00",
            "timezone": "Europe/Warsaw",
            "runtime_mode": "process_turn",
            "client": "test",
            "lifecycle": "one_shot",
        },
        "response_format": {"timezone": "Europe/Warsaw"},
    }


def test_lineage_ids_are_stable_opaque_and_do_not_embed_payload_text() -> None:
    turn_id = str(uuid.uuid4())
    trace_id = str(uuid.uuid4())
    secret_goal = "porównaj bardzo prywatny dokument A z dokumentem B"
    secret_constraint = "nie ujawniaj sekretu użytkownika"
    secret_evidence = "source_locator:/private/user/archive/episode-42"

    first = CognitiveLineage.create(turn_id=turn_id, trace_id=trace_id)
    observed = first.observe(
        stage="dialogue_control",
        event="semantic_anchors_selected",
        source="test",
        goal_refs=(secret_goal,),
        constraint_refs=(secret_constraint,),
        evidence_refs=(secret_evidence,),
        anchor_categories=("goal", "constraint", "evidence"),
    )
    repeated = first.observe(
        stage="handler",
        event="handoff",
        source="test",
        goal_refs=(secret_goal,),
        constraint_refs=(secret_constraint,),
        evidence_refs=(secret_evidence,),
        expect_categories=("goal", "constraint", "evidence"),
    )

    second = CognitiveLineage.create(turn_id=turn_id, trace_id=trace_id)
    repeated_second = second.observe(
        stage="dialogue_control",
        event="semantic_anchors_selected",
        source="test",
        goal_refs=(secret_goal,),
        constraint_refs=(secret_constraint,),
        evidence_refs=(secret_evidence,),
        anchor_categories=("goal", "constraint", "evidence"),
    )

    assert first.thought_id == second.thought_id
    assert observed.goal_ids == repeated.goal_ids == repeated_second.goal_ids
    assert observed.constraint_ids == repeated.constraint_ids == repeated_second.constraint_ids
    assert observed.evidence_ids == repeated.evidence_ids == repeated_second.evidence_ids
    assert repeated.continuity_ok is True

    serialized = json.dumps(first.to_dict(), ensure_ascii=False, sort_keys=True)
    assert secret_goal not in serialized
    assert secret_constraint not in serialized
    assert secret_evidence not in serialized


def test_lineage_detects_silent_goal_loss_instead_of_carrying_it_forward() -> None:
    lineage = CognitiveLineage.create(
        turn_id=str(uuid.uuid4()),
        trace_id=str(uuid.uuid4()),
    )
    anchored = lineage.observe(
        stage="dialogue_control",
        event="anchors",
        source="test",
        goal_refs=("active-goal",),
        constraint_refs=("exact_runtime_required=True",),
        anchor_categories=("goal", "constraint"),
    )
    assert anchored.continuity_ok is True

    handoff = lineage.observe(
        stage="route_handler",
        event="handoff",
        source="test",
        constraint_refs=("exact_runtime_required=True",),
        expect_categories=("goal", "constraint"),
    )

    assert handoff.continuity_ok is False
    assert set(handoff.missing_required_ids) == {"goal"}
    assert handoff.missing_required_ids["goal"] == tuple(lineage.anchored_goal_ids)
    assert lineage.lineage_break_count == 1


def test_parent_thought_link_is_explicit_only() -> None:
    parent = str(uuid.uuid4())
    assert resolve_parent_thought_id({}) is None
    assert resolve_parent_thought_id({"previous_task_state": {"thought_id": parent}}) is None
    assert resolve_parent_thought_id({"previous_thought_id": "not-a-uuid"}) is None
    assert resolve_parent_thought_id({"previous_thought_id": parent}) == parent
    assert resolve_parent_thought_id({"previous_cognitive_lineage": {"thought_id": parent}}) == parent


def test_evidence_reference_extraction_ignores_recalled_content() -> None:
    base = {
        "items": [
            {
                "content": "bardzo prywatna treść pamięci",
                "source": "archive",
                "memory_type": "living_memory:l2",
                "timestamp": "2026-08-01T10:00:00+00:00",
                "metadata": {"memory_id": "mem-42", "source_locator": "row:42"},
            }
        ]
    }
    changed_content = {
        "items": [
            {
                **base["items"][0],
                "content": "zupełnie inna treść tego samego rekordu",
            }
        ]
    }

    refs_a = evidence_references_from_memory_contract(base)
    refs_b = evidence_references_from_memory_contract(changed_content)

    assert refs_a == refs_b
    assert len(refs_a) == 1
    assert "bardzo prywatna treść" not in refs_a[0]
    assert "zupełnie inna treść" not in refs_a[0]


def test_constraint_references_are_limited_to_control_plane_fields() -> None:
    refs = constraint_references_from_policy(
        {
            "exact_runtime_required": True,
            "allow_memory_content": False,
            "answer_kind": "exact_runtime_quote",
            "user_private_note": "do not include me",
            "arbitrary_nested": {"secret": "x"},
        }
    )

    joined = "|".join(refs)
    assert "exact_runtime_required=True" in refs
    assert "allow_memory_content=False" in refs
    assert "answer_kind=exact_runtime_quote" in refs
    assert "user_private_note" not in joined
    assert "arbitrary_nested" not in joined


def test_cognitive_turn_envelope_adds_shadow_lineage_without_mutating_input_frame() -> None:
    turn_id = str(uuid.uuid4())
    trace_id = str(uuid.uuid4())
    parent = str(uuid.uuid4())
    frame = _frame(turn_id=turn_id, trace_id=trace_id)

    envelope = CognitiveTurnEnvelope.from_cognitive_frame(
        frame,
        user_text="test",
        client_context={"previous_thought_id": parent},
    )

    assert "cognitive_lineage" not in frame
    assert envelope.cognitive_lineage.turn_id == turn_id
    assert envelope.cognitive_lineage.trace_id == trace_id
    assert envelope.cognitive_lineage.parent_thought_id == parent
    assert envelope.cognitive_lineage.shadow_mode is True
    assert envelope.cognitive_frame["cognitive_lineage"]["thought_id"] == envelope.cognitive_lineage.thought_id

    observation = envelope.observe_cognitive_lineage(
        stage="dialogue_control",
        event="goal_selected",
        source="test",
        goal_refs=("goal",),
        anchor_categories=("goal",),
    )
    serialized = envelope.to_dict()
    assert observation["continuity_ok"] is True
    assert serialized["cognitive_lineage"]["thought_id"] == envelope.cognitive_lineage.thought_id
    assert serialized["cognitive_frame"]["cognitive_lineage"]["observation_count"] >= 2


def test_turn_route_trace_can_surface_lineage_summary_without_replacing_route_trace() -> None:
    lineage = CognitiveLineage.create(
        turn_id=str(uuid.uuid4()),
        trace_id=str(uuid.uuid4()),
    )
    lineage.observe(
        stage="dialogue_control",
        event="anchors",
        source="test",
        goal_refs=("goal",),
        constraint_refs=("constraint",),
        anchor_categories=("goal", "constraint"),
    )
    summary = lineage.summary()

    trace = TurnRouteTrace(
        selected_route="ordinary_dialogue",
        thought_id=summary["thought_id"],
        parent_thought_id=summary["parent_thought_id"],
        anchored_goal_ids=summary["anchored_goal_ids"],
        anchored_constraint_ids=summary["anchored_constraint_ids"],
        anchored_evidence_ids=summary["anchored_evidence_ids"],
        lineage_observation_count=summary["lineage_observation_count"],
        lineage_break_count=summary["lineage_break_count"],
        lineage_state_sha256=summary["lineage_state_sha256"],
        lineage_shadow_mode=summary["lineage_shadow_mode"],
    ).to_dict()

    assert trace["selected_route"] == "ordinary_dialogue"
    assert trace["thought_id"] == lineage.thought_id
    assert trace["anchored_goal_ids"] == lineage.anchored_goal_ids
    assert trace["lineage_shadow_mode"] is True


def test_envelope_observes_runtime_decision_and_syncs_lineage_into_route_trace() -> None:
    turn_id = str(uuid.uuid4())
    trace_id = str(uuid.uuid4())
    frame = _frame(turn_id=turn_id, trace_id=trace_id)
    frame["memory_recall_contract"] = {
        "items": [
            {
                "item_id": "memory-item-1",
                "content": "private recalled payload that must not enter lineage",
                "source": "living_memory:l2",
            }
        ]
    }
    frame["dialogue_task_state"] = {"active_goal": "prepare the requested upgrade"}
    frame["turn_response_policy"] = {
        "exact_runtime_required": False,
        "allow_memory_content": True,
        "answer_kind": "ordinary_dialogue",
    }
    envelope = CognitiveTurnEnvelope.from_cognitive_frame(frame, user_text="test")

    decision = {
        "route": "ordinary_dialogue",
        "dialogue_task_state": {"active_goal": "prepare the requested upgrade"},
        "turn_response_policy": dict(frame["turn_response_policy"]),
        "model_guided_synthesis": {
            "sources": [{"item_id": "memory-item-1", "source": "living_memory:l2"}],
            "candidate_validation": {"candidate_id": "candidate-7"},
        },
        "turn_route_trace": {"schema_version": "turn_route_trace/v1", "selected_route": "ordinary_dialogue"},
    }
    envelope.attach_conversation_decision(decision)

    trace = envelope.conversation_decision["turn_route_trace"]
    assert trace["thought_id"] == envelope.cognitive_lineage.thought_id
    assert trace["lineage_shadow_mode"] is True
    assert trace["lineage_observation_count"] >= 3
    assert trace["lineage_break_count"] == 0
    assert envelope.cognitive_lineage.anchored_goal_ids
    assert envelope.cognitive_lineage.anchored_constraint_ids
    assert envelope.cognitive_lineage.anchored_evidence_ids
    serialized_lineage = json.dumps(envelope.cognitive_lineage.to_dict(), ensure_ascii=False, sort_keys=True)
    assert "private recalled payload" not in serialized_lineage


def test_finalization_records_lineage_without_changing_visible_text() -> None:
    turn_id = str(uuid.uuid4())
    trace_id = str(uuid.uuid4())
    frame = _frame(turn_id=turn_id, trace_id=trace_id)
    frame["dialogue_task_state"] = {"active_goal": "goal"}
    frame["turn_response_policy"] = {"exact_runtime_required": False}
    envelope = CognitiveTurnEnvelope.from_cognitive_frame(frame, user_text="test")
    envelope.attach_conversation_decision(
        {
            "route": "ordinary_dialogue",
            "dialogue_task_state": {"active_goal": "goal"},
            "turn_response_policy": {"exact_runtime_required": False},
            "turn_route_trace": {"schema_version": "turn_route_trace/v1"},
        }
    )
    visible = "🕒 2026-08-14 22:00:00\n🌿 Łatka\n\nGotowe."
    envelope.attach_final_response_contract({"schema_version": "final_response/v1"}, visible)

    assert envelope.final_visible_text == visible
    assert envelope.cognitive_lineage.latest_observation is not None
    assert envelope.cognitive_lineage.latest_observation.stage == "final_response_contract"
    assert envelope.cognitive_lineage.lineage_break_count == 0
