from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from latka_jazn.core.cognitive_state_graph import CognitiveStateGraph
from latka_jazn.version import schema_version


SCHEMA_VERSION = schema_version("global_salience_controller")

_KIND_WEIGHT = {
    "goal": 0.36,
    "constraint": 0.34,
    "conflict": 0.32,
    "question": 0.28,
    "evidence": 0.25,
    "claim": 0.22,
    "tool_result": 0.20,
    "action": 0.18,
    "route": 0.16,
    "candidate": 0.14,
    "assumption": 0.10,
    "thought": 0.08,
}


@dataclass(slots=True, frozen=True)
class SalienceItem:
    node_id: str
    node_kind: str
    score: float
    pinned: bool
    features: dict[str, float]
    reason_codes: tuple[str, ...]
    schema_version: str = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["reason_codes"] = list(self.reason_codes)
        return data


@dataclass(slots=True, frozen=True)
class SalienceDecision:
    status: str
    selected_node_ids: tuple[str, ...]
    pinned_goal_ids: tuple[str, ...]
    pinned_constraint_ids: tuple[str, ...]
    items: tuple[SalienceItem, ...]
    considered_node_count: int
    input_truncated: bool
    truth_gate_precedence: bool = True
    route_override_allowed: bool = False
    fact_creation_allowed: bool = False
    memory_promotion_allowed: bool = False
    private_reasoning_recorded: bool = False
    schema_version: str = SCHEMA_VERSION
    truth_boundary: str = (
        "Salience is a deterministic ranking of bounded observable graph features. "
        "It does not contain private reasoning, create claims, authorize memory promotion, "
        "or override an explicit user route or any truth gate."
    )

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["selected_node_ids"] = list(self.selected_node_ids)
        data["pinned_goal_ids"] = list(self.pinned_goal_ids)
        data["pinned_constraint_ids"] = list(self.pinned_constraint_ids)
        data["items"] = [item.to_dict() for item in self.items]
        return data


class GlobalSalienceController:
    """Bounded deterministic controller over opaque Cognitive State Graph nodes."""

    def __init__(self, *, max_considered_nodes: int = 128, max_selected_nodes: int = 24) -> None:
        self.max_considered_nodes = max(8, min(512, int(max_considered_nodes)))
        self.max_selected_nodes = max(4, min(64, int(max_selected_nodes)))

    def evaluate(self, graph: CognitiveStateGraph) -> SalienceDecision:
        all_nodes = [graph.nodes[key] for key in sorted(graph.nodes)]
        active_anchors = [
            node
            for node in all_nodes
            if node.status == "active" and node.kind in {"goal", "constraint"}
        ]
        anchor_ids = {node.node_id for node in active_anchors}
        considered = (
            active_anchors
            + [node for node in all_nodes if node.node_id not in anchor_ids]
        )[: self.max_considered_nodes]
        degree: dict[str, int] = {node.node_id: 0 for node in considered}
        relation_flags: dict[str, set[str]] = {node.node_id: set() for node in considered}
        allowed_ids = set(degree)
        for edge in graph.edges:
            if edge.source_node_id in allowed_ids:
                degree[edge.source_node_id] += 1
                relation_flags[edge.source_node_id].add(edge.relation)
            if edge.target_node_id in allowed_ids:
                degree[edge.target_node_id] += 1
                relation_flags[edge.target_node_id].add(edge.relation)

        latest_sequence = max(
            (node.last_observed_sequence for node in considered),
            default=0,
        )
        scored: list[SalienceItem] = []
        for node in considered:
            age = max(0, latest_sequence - node.last_observed_sequence)
            recency = 1.0 / (1.0 + float(age))
            connectivity = min(1.0, degree[node.node_id] / 6.0)
            active = 1.0 if node.status == "active" else 0.0
            explicit_conflict = 1.0 if (
                node.kind == "conflict"
                or bool({"contradicts", "supersedes"} & relation_flags[node.node_id])
            ) else 0.0
            selected_evidence = 1.0 if (
                node.kind == "evidence"
                and bool({"supports", "selected_for_candidate", "available_for_goal"} & relation_flags[node.node_id])
            ) else 0.0
            pinned = bool(node.status == "active" and node.kind in {"goal", "constraint"})
            score = min(1.0, max(0.0,
                _KIND_WEIGHT.get(node.kind, 0.06)
                + 0.18 * recency
                + 0.12 * connectivity
                + 0.10 * active
                + 0.12 * explicit_conflict
                + 0.10 * selected_evidence
            ))
            reasons = [f"kind:{node.kind}"]
            if pinned:
                reasons.append("active_anchor_pinned")
            if recency >= 0.5:
                reasons.append("recently_observed")
            if connectivity > 0:
                reasons.append("graph_connected")
            if explicit_conflict:
                reasons.append("explicit_conflict_relation")
            if selected_evidence:
                reasons.append("explicit_evidence_relation")
            scored.append(SalienceItem(
                node_id=node.node_id,
                node_kind=node.kind,
                score=round(score, 6),
                pinned=pinned,
                features={
                    "kind_weight": _KIND_WEIGHT.get(node.kind, 0.06),
                    "recency": round(recency, 6),
                    "connectivity": round(connectivity, 6),
                    "active": active,
                    "explicit_conflict": explicit_conflict,
                    "selected_evidence": selected_evidence,
                },
                reason_codes=tuple(reasons),
            ))

        scored.sort(key=lambda item: (-int(item.pinned), -item.score, item.node_id))
        pinned = [item for item in scored if item.pinned]
        if len(active_anchors) > self.max_considered_nodes or len(pinned) > self.max_selected_nodes:
            return SalienceDecision(
                status="blocked_active_anchor_overflow",
                selected_node_ids=(),
                pinned_goal_ids=tuple(sorted(node.node_id for node in active_anchors if node.kind == "goal")),
                pinned_constraint_ids=tuple(sorted(node.node_id for node in active_anchors if node.kind == "constraint")),
                items=tuple(scored[: self.max_selected_nodes]),
                considered_node_count=len(considered),
                input_truncated=len(all_nodes) > len(considered),
            )
        selected = scored[: self.max_selected_nodes]
        return SalienceDecision(
            status="ready",
            selected_node_ids=tuple(item.node_id for item in selected),
            pinned_goal_ids=tuple(item.node_id for item in pinned if item.node_kind == "goal"),
            pinned_constraint_ids=tuple(item.node_id for item in pinned if item.node_kind == "constraint"),
            items=tuple(selected),
            considered_node_count=len(considered),
            input_truncated=len(all_nodes) > len(considered),
        )


def build_cognitive_control_policy(decision: SalienceDecision) -> dict[str, Any]:
    kinds = {item.node_kind for item in decision.items}
    hints: list[str] = ["do_not_emit_private_reasoning"]
    if decision.status == "ready" and decision.pinned_goal_ids:
        hints.append("preserve_active_goal")
    if decision.status == "ready" and decision.pinned_constraint_ids:
        hints.append("preserve_active_constraints")
    if decision.status == "ready" and "evidence" in kinds:
        hints.append("ground_claims_in_selected_evidence")
    if decision.status == "ready" and ("conflict" in kinds or any(
        "explicit_conflict_relation" in item.reason_codes for item in decision.items
    )):
        hints.append("surface_explicit_conflict_without_inventing_resolution")
    return {
        "schema_version": schema_version("cognitive_control_policy"),
        "status": decision.status,
        "salience_selected_node_ids": list(decision.selected_node_ids),
        "working_memory_pinned_goal_ids": list(decision.pinned_goal_ids),
        "working_memory_pinned_constraint_ids": list(decision.pinned_constraint_ids),
        "generation_hints": hints,
        "truth_gate_precedence": True,
        "route_override_allowed": False,
        "fact_creation_allowed": False,
        "memory_promotion_allowed": False,
        "private_reasoning_recorded": False,
        "truth_boundary": (
            "This policy may prioritize already explicit goals, constraints and evidence only. "
            "Truth gates, user intent and promotion gates always take precedence."
        ),
    }


__all__ = [
    "GlobalSalienceController",
    "SalienceDecision",
    "SalienceItem",
    "build_cognitive_control_policy",
]
