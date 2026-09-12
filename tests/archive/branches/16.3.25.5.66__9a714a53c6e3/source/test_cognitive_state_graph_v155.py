from __future__ import annotations

import json
import uuid

from latka_jazn.core.cognitive_lineage import CognitiveLineage
from latka_jazn.core.cognitive_state_graph import CognitiveStateGraph
from latka_jazn.core.cognitive_turn_envelope import CognitiveTurnEnvelope


def _frame(*, turn_id: str, trace_id: str) -> dict:
    return {
        "schema_version": "chatgpt_cognitive_frame/v1",
        "runtime_version": "v15.4.2.1",
        "timestamp": "🕒 2026-08-14 23:30:00",
        "turn_id": turn_id,
        "trace_id": trace_id,
        "turn_trace": {
            "schema_version": "turn_trace/v1",
            "turn_id": turn_id,
            "trace_id": trace_id,
            "timestamp_header": "🕒 2026-08-14 23:30:00",
            "timezone": "Europe/Warsaw",
            "runtime_mode": "process_turn",
            "client": "test",
            "lifecycle": "one_shot",
        },
        "response_format": {"timezone": "Europe/Warsaw"},
    }


def _edge_relations(graph: CognitiveStateGraph) -> set[tuple[str, str, str]]:
    return {
        (edge.source_node_id, edge.target_node_id, edge.relation)
        for edge in graph.edges
    }


def test_state_graph_projects_lineage_into_typed_operational_nodes() -> None:
    lineage = CognitiveLineage.create(
        turn_id=str(uuid.uuid4()),
        trace_id=str(uuid.uuid4()),
    )
    observation = lineage.observe(
        stage="conversation_decision",
        event="runtime_decision_observed",
        source="test",
        goal_refs=("private goal payload",),
        constraint_refs=("exact_runtime_required=True",),
        evidence_refs=("memory_id:42",),
        route_ref="ordinary_dialogue",
        candidate_ref="candidate-1",
        anchor_categories=("goal", "constraint", "evidence"),
    )

    graph = CognitiveStateGraph.create(lineage)

    assert graph.shadow_mode is False
    assert graph.control_mode == "policy_bounded"
    assert graph.nodes[graph.thought_id].kind == "thought"
    assert {graph.nodes[node_id].kind for node_id in observation.goal_ids} == {"goal"}
    assert {graph.nodes[node_id].kind for node_id in observation.constraint_ids} == {"constraint"}
    assert {graph.nodes[node_id].kind for node_id in observation.evidence_ids} == {"evidence"}
    assert observation.route_id is not None and graph.nodes[observation.route_id].kind == "route"
    assert observation.candidate_id is not None and graph.nodes[observation.candidate_id].kind == "candidate"

    serialized = json.dumps(graph.to_dict(), ensure_ascii=False, sort_keys=True)
    assert "private goal payload" not in serialized
    assert "exact_runtime_required=True" not in serialized
    assert "memory_id:42" not in serialized


def test_state_graph_records_only_relations_supported_by_runtime_handoff() -> None:
    lineage = CognitiveLineage.create(
        turn_id=str(uuid.uuid4()),
        trace_id=str(uuid.uuid4()),
    )
    observation = lineage.observe(
        stage="conversation_decision",
        event="runtime_decision_observed",
        source="test",
        goal_refs=("goal",),
        constraint_refs=("constraint",),
        evidence_refs=("evidence",),
        route_ref="route",
        candidate_ref="candidate",
        anchor_categories=("goal", "constraint", "evidence"),
    )
    graph = CognitiveStateGraph.create(lineage)
    relations = _edge_relations(graph)

    goal_id = observation.goal_ids[0]
    constraint_id = observation.constraint_ids[0]
    evidence_id = observation.evidence_ids[0]
    assert observation.route_id is not None
    assert observation.candidate_id is not None

    assert (constraint_id, goal_id, "constrains") in relations
    assert (observation.route_id, goal_id, "selected_for") in relations
    assert (observation.candidate_id, observation.route_id, "produced_on") in relations
    assert (evidence_id, observation.candidate_id, "selected_for_candidate") in relations
    assert all("supports" not in relation for _, _, relation in relations)


def test_state_graph_preserves_old_node_when_it_is_explicitly_superseded() -> None:
    lineage = CognitiveLineage.create(
        turn_id=str(uuid.uuid4()),
        trace_id=str(uuid.uuid4()),
    )
    graph = CognitiveStateGraph.create(lineage)
    old_id = str(uuid.uuid4())
    new_id = str(uuid.uuid4())
    graph.append_explicit_node(
        node_id=old_id,
        kind="goal",
        source="test",
        stage="dialogue_task_state",
        event="goal_observed",
    )

    edge = graph.supersede_node(
        previous_node_id=old_id,
        replacement_node_id=new_id,
        replacement_kind="goal",
        source="test",
        reason_code="user_changed_goal",
    )

    assert old_id in graph.nodes
    assert new_id in graph.nodes
    assert graph.nodes[old_id].status == "superseded"
    assert graph.nodes[new_id].status == "active"
    assert edge.source_node_id == new_id
    assert edge.target_node_id == old_id
    assert edge.relation == "supersedes"
    assert edge.reason_code == "user_changed_goal"


def test_state_graph_mirrors_lineage_break_without_deleting_missing_node() -> None:
    lineage = CognitiveLineage.create(
        turn_id=str(uuid.uuid4()),
        trace_id=str(uuid.uuid4()),
    )
    anchored = lineage.observe(
        stage="dialogue_control",
        event="anchors",
        source="test",
        goal_refs=("goal",),
        anchor_categories=("goal",),
    )
    graph = CognitiveStateGraph.create(lineage)
    missing_goal_id = anchored.goal_ids[0]

    broken = lineage.observe(
        stage="handler",
        event="handoff",
        source="test",
        expect_categories=("goal",),
    )
    transition = graph.observe_lineage_observation(broken)

    assert broken.continuity_ok is False
    assert transition.continuity_ok is False
    assert graph.graph_break_count == 1
    assert missing_goal_id in graph.nodes
    assert graph.nodes[missing_goal_id].status == "active"
    assert transition.missing_required_ids["goal"] == (missing_goal_id,)


def test_state_graph_round_trip_preserves_operational_history() -> None:
    lineage = CognitiveLineage.create(
        turn_id=str(uuid.uuid4()),
        trace_id=str(uuid.uuid4()),
    )
    lineage.observe(
        stage="decision",
        event="observed",
        source="test",
        goal_refs=("goal",),
        route_ref="route",
        anchor_categories=("goal",),
    )
    graph = CognitiveStateGraph.create(lineage)
    payload = graph.to_dict()

    restored = CognitiveStateGraph.from_dict(payload)

    assert restored.to_dict() == payload
    assert restored.latest_state_sha256 == graph.latest_state_sha256


def test_envelope_exposes_state_graph_and_syncs_summary_into_route_trace() -> None:
    turn_id = str(uuid.uuid4())
    trace_id = str(uuid.uuid4())
    frame = _frame(turn_id=turn_id, trace_id=trace_id)
    frame["memory_recall_contract"] = {
        "items": [
            {
                "item_id": "memory-1",
                "content": "private memory content",
                "source": "living_memory:l2",
            }
        ]
    }
    frame["dialogue_task_state"] = {"active_goal": "prepare upgrade"}
    frame["turn_response_policy"] = {
        "exact_runtime_required": False,
        "allow_memory_content": True,
        "answer_kind": "ordinary_dialogue",
    }
    envelope = CognitiveTurnEnvelope.from_cognitive_frame(frame, user_text="test")
    envelope.attach_conversation_decision(
        {
            "route": "ordinary_dialogue",
            "dialogue_task_state": {"active_goal": "prepare upgrade"},
            "turn_response_policy": dict(frame["turn_response_policy"]),
            "model_guided_synthesis": {
                "sources": [{"item_id": "memory-1", "source": "living_memory:l2"}],
                "candidate_validation": {"candidate_id": "candidate-1"},
            },
            "turn_route_trace": {
                "schema_version": "turn_route_trace/v1",
                "selected_route": "ordinary_dialogue",
            },
        }
    )

    graph_payload = envelope.cognitive_frame["cognitive_state_graph"]
    route_trace = envelope.conversation_decision["turn_route_trace"]

    assert graph_payload["thought_id"] == envelope.cognitive_lineage.thought_id
    assert graph_payload["node_count"] >= 6
    assert route_trace["state_graph_node_count"] == graph_payload["node_count"]
    assert route_trace["state_graph_edge_count"] == graph_payload["edge_count"]
    assert route_trace["state_graph_transition_count"] == graph_payload["transition_count"]
    assert route_trace["state_graph_break_count"] == 0
    assert route_trace["state_graph_shadow_mode"] is False
    assert route_trace["state_graph_control_mode"] == "policy_bounded"
    assert "private memory content" not in json.dumps(graph_payload, ensure_ascii=False)


def test_finalization_appends_graph_transition_without_changing_visible_text() -> None:
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
    before = len(envelope.cognitive_state_graph.transitions)
    visible = "🕒 2026-08-14 23:30:00\n🌿 Łatka\n\nGotowe."

    envelope.attach_final_response_contract({"schema_version": "final_response/v1"}, visible)

    assert envelope.final_visible_text == visible
    assert len(envelope.cognitive_state_graph.transitions) == before + 1
    assert envelope.cognitive_state_graph.transitions[-1].stage == "final_response_contract"
    assert envelope.cognitive_state_graph.graph_break_count == 0
