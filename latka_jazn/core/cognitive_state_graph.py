from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import json
from typing import Any, Iterable

from latka_jazn.core.cognitive_lineage import CognitiveLineage, CognitiveLineageObservation
from latka_jazn.version import schema_version

SCHEMA_VERSION = schema_version("cognitive_state_graph")
NODE_SCHEMA_VERSION = schema_version("cognitive_state_node")
EDGE_SCHEMA_VERSION = schema_version("cognitive_state_edge")
TRANSITION_SCHEMA_VERSION = schema_version("cognitive_state_transition")

_NODE_KINDS = frozenset(
    {
        "thought",
        "goal",
        "constraint",
        "assumption",
        "question",
        "evidence",
        "tool_result",
        "claim",
        "conflict",
        "action",
        "route",
        "candidate",
    }
)
_NODE_STATUSES = frozenset({"active", "superseded", "resolved", "consumed"})


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _clean_token(value: Any, *, fallback: str) -> str:
    text = str(value or "").strip().lower()
    cleaned = "".join(ch if ch.isalnum() or ch in "._:/-" else "_" for ch in text)
    return cleaned.strip("_") or fallback


def _normalize_ids(values: Iterable[Any] | None) -> tuple[str, ...]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in values or ():
        value = str(raw or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        out.append(value)
    return tuple(out)


def _edge_id(source_node_id: str, target_node_id: str, relation: str) -> str:
    return _sha256_json(
        {
            "source_node_id": source_node_id,
            "target_node_id": target_node_id,
            "relation": relation,
        }
    )


@dataclass(slots=True)
class CognitiveStateNode:
    node_id: str
    kind: str
    source: str
    created_sequence: int
    last_observed_sequence: int
    status: str = "active"
    schema_version: str = NODE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        self.node_id = str(self.node_id or "").strip()
        if not self.node_id:
            raise ValueError("node_id is required")
        self.kind = _clean_token(self.kind, fallback="unknown")
        if self.kind not in _NODE_KINDS:
            raise ValueError(f"unsupported cognitive state node kind: {self.kind}")
        self.source = _clean_token(self.source, fallback="runtime")
        self.created_sequence = max(0, int(self.created_sequence or 0))
        self.last_observed_sequence = max(self.created_sequence, int(self.last_observed_sequence or 0))
        self.status = _clean_token(self.status, fallback="active")
        if self.status not in _NODE_STATUSES:
            raise ValueError(f"unsupported cognitive state node status: {self.status}")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True, frozen=True)
class CognitiveStateEdge:
    edge_id: str
    source_node_id: str
    target_node_id: str
    relation: str
    source: str
    created_sequence: int
    reason_code: str | None = None
    schema_version: str = EDGE_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True, frozen=True)
class CognitiveStateTransition:
    sequence: int
    stage: str
    event: str
    source: str
    observed_node_ids: tuple[str, ...] = ()
    missing_required_ids: dict[str, tuple[str, ...]] = field(default_factory=dict)
    continuity_ok: bool = True
    state_sha256: str = ""
    schema_version: str = TRANSITION_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["observed_node_ids"] = list(self.observed_node_ids)
        data["missing_required_ids"] = {
            key: list(value) for key, value in self.missing_required_ids.items()
        }
        return data


@dataclass(slots=True)
class CognitiveStateGraph:
    """Append-only operational graph for one runtime turn.

    The graph records explicit runtime artefacts and hand-off relations using
    opaque identifiers already produced by cognitive lineage. It does not store
    user text, recalled memory content or private chain-of-thought, and it does
    not store free-form reasoning. A separate bounded controller may consume
    observable graph features, but truth gates and explicit user intent prevail.
    """

    thought_id: str
    turn_id: str
    trace_id: str
    parent_thought_id: str | None = None
    nodes: dict[str, CognitiveStateNode] = field(default_factory=dict)
    edges: list[CognitiveStateEdge] = field(default_factory=list)
    transitions: list[CognitiveStateTransition] = field(default_factory=list)
    graph_break_count: int = 0
    shadow_mode: bool = False
    control_mode: str = "policy_bounded"
    schema_version: str = SCHEMA_VERSION
    truth_boundary: str = (
        "Cognitive State Graph is an operational, append-only correlation graph. "
        "It is not private chain-of-thought, biological cognition, a truth proof, "
        "or an autonomous controller. Nodes contain opaque runtime identifiers. "
        "Only a bounded policy controller may rank explicit nodes, and it cannot "
        "create facts, promote memory or override truth gates or user intent."
    )

    @classmethod
    def create(cls, lineage: CognitiveLineage) -> "CognitiveStateGraph":
        graph = cls(
            thought_id=str(lineage.thought_id),
            turn_id=str(lineage.turn_id),
            trace_id=str(lineage.trace_id),
            parent_thought_id=lineage.parent_thought_id,
        )
        graph._ensure_node(
            graph.thought_id,
            kind="thought",
            source="cognitive_lineage",
            sequence=0,
        )
        for observation in lineage.observations:
            graph.observe_lineage_observation(observation)
        return graph

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "CognitiveStateGraph":
        data = dict(payload or {})
        graph = cls(
            thought_id=str(data.get("thought_id") or "").strip(),
            turn_id=str(data.get("turn_id") or "").strip(),
            trace_id=str(data.get("trace_id") or "").strip(),
            parent_thought_id=(str(data.get("parent_thought_id")).strip() if data.get("parent_thought_id") else None),
            graph_break_count=max(0, int(data.get("graph_break_count") or 0)),
            shadow_mode=bool(data.get("shadow_mode", False)),
            control_mode=_clean_token(data.get("control_mode"), fallback="policy_bounded"),
        )
        if not graph.thought_id or not graph.turn_id or not graph.trace_id:
            raise ValueError("thought_id, turn_id and trace_id are required for cognitive state graph")
        for raw in data.get("nodes") or []:
            if not isinstance(raw, dict):
                continue
            node = CognitiveStateNode(
                node_id=str(raw.get("node_id") or ""),
                kind=str(raw.get("kind") or ""),
                source=str(raw.get("source") or "runtime"),
                created_sequence=int(raw.get("created_sequence") or 0),
                last_observed_sequence=int(raw.get("last_observed_sequence") or 0),
                status=str(raw.get("status") or "active"),
                schema_version=str(raw.get("schema_version") or NODE_SCHEMA_VERSION),
            )
            graph.nodes[node.node_id] = node
        if graph.thought_id not in graph.nodes:
            graph._ensure_node(
                graph.thought_id,
                kind="thought",
                source="cognitive_lineage",
                sequence=0,
            )
        for raw in data.get("edges") or []:
            if not isinstance(raw, dict):
                continue
            source_node_id = str(raw.get("source_node_id") or "").strip()
            target_node_id = str(raw.get("target_node_id") or "").strip()
            if source_node_id not in graph.nodes or target_node_id not in graph.nodes:
                raise ValueError("serialized cognitive state edge references a missing node")
            edge = CognitiveStateEdge(
                edge_id=str(raw.get("edge_id") or _edge_id(source_node_id, target_node_id, str(raw.get("relation") or "related_to"))),
                source_node_id=source_node_id,
                target_node_id=target_node_id,
                relation=_clean_token(raw.get("relation"), fallback="related_to"),
                source=_clean_token(raw.get("source"), fallback="runtime"),
                created_sequence=max(0, int(raw.get("created_sequence") or 0)),
                reason_code=(str(raw.get("reason_code")).strip() if raw.get("reason_code") else None),
                schema_version=str(raw.get("schema_version") or EDGE_SCHEMA_VERSION),
            )
            graph.edges.append(edge)
        graph.edges.sort(key=lambda item: item.edge_id)
        for raw in data.get("transitions") or []:
            if not isinstance(raw, dict):
                continue
            missing_raw = raw.get("missing_required_ids")
            missing = {
                str(key): _normalize_ids(value if isinstance(value, (list, tuple)) else ())
                for key, value in (missing_raw.items() if isinstance(missing_raw, dict) else [])
            }
            transition = CognitiveStateTransition(
                sequence=max(1, int(raw.get("sequence") or (len(graph.transitions) + 1))),
                stage=_clean_token(raw.get("stage"), fallback="unknown_stage"),
                event=_clean_token(raw.get("event"), fallback="observation"),
                source=_clean_token(raw.get("source"), fallback="runtime"),
                observed_node_ids=_normalize_ids(raw.get("observed_node_ids") if isinstance(raw.get("observed_node_ids"), (list, tuple)) else ()),
                missing_required_ids=missing,
                continuity_ok=bool(raw.get("continuity_ok", True)),
                state_sha256=str(raw.get("state_sha256") or ""),
                schema_version=str(raw.get("schema_version") or TRANSITION_SCHEMA_VERSION),
            )
            graph.transitions.append(transition)
        return graph

    def _ensure_node(
        self,
        node_id: str,
        *,
        kind: str,
        source: str,
        sequence: int,
    ) -> CognitiveStateNode:
        normalized_id = str(node_id or "").strip()
        if not normalized_id:
            raise ValueError("node_id is required")
        normalized_kind = _clean_token(kind, fallback="unknown")
        if normalized_kind not in _NODE_KINDS:
            raise ValueError(f"unsupported cognitive state node kind: {normalized_kind}")
        existing = self.nodes.get(normalized_id)
        if existing is not None:
            if existing.kind != normalized_kind:
                raise ValueError(
                    f"node kind mismatch for {normalized_id}: {existing.kind}!={normalized_kind}"
                )
            existing.last_observed_sequence = max(existing.last_observed_sequence, int(sequence or 0))
            return existing
        node = CognitiveStateNode(
            node_id=normalized_id,
            kind=normalized_kind,
            source=source,
            created_sequence=int(sequence or 0),
            last_observed_sequence=int(sequence or 0),
        )
        self.nodes[normalized_id] = node
        return node

    def _ensure_edge(
        self,
        source_node_id: str,
        target_node_id: str,
        *,
        relation: str,
        source: str,
        sequence: int,
        reason_code: str | None = None,
    ) -> CognitiveStateEdge:
        if source_node_id not in self.nodes or target_node_id not in self.nodes:
            raise ValueError("cognitive state edges require existing source and target nodes")
        relation_token = _clean_token(relation, fallback="related_to")
        identifier = _edge_id(source_node_id, target_node_id, relation_token)
        for edge in self.edges:
            if edge.edge_id == identifier:
                return edge
        edge = CognitiveStateEdge(
            edge_id=identifier,
            source_node_id=source_node_id,
            target_node_id=target_node_id,
            relation=relation_token,
            source=_clean_token(source, fallback="runtime"),
            created_sequence=max(0, int(sequence or 0)),
            reason_code=(
                _clean_token(reason_code, fallback="unspecified") if reason_code else None
            ),
        )
        self.edges.append(edge)
        self.edges.sort(key=lambda item: item.edge_id)
        return edge

    def _link_part_of_thought(self, node_ids: Iterable[str], *, source: str, sequence: int) -> None:
        for node_id in _normalize_ids(node_ids):
            if node_id == self.thought_id:
                continue
            self._ensure_edge(
                node_id,
                self.thought_id,
                relation="part_of",
                source=source,
                sequence=sequence,
            )

    def observe_lineage_observation(
        self,
        observation: CognitiveLineageObservation,
    ) -> CognitiveStateTransition:
        sequence = max(len(self.transitions) + 1, int(observation.sequence or 0))
        source = _clean_token(observation.source, fallback="runtime")
        goals = _normalize_ids(observation.goal_ids)
        constraints = _normalize_ids(observation.constraint_ids)
        evidence = _normalize_ids(observation.evidence_ids)

        for node_id in goals:
            self._ensure_node(node_id, kind="goal", source=source, sequence=sequence)
        for node_id in constraints:
            self._ensure_node(node_id, kind="constraint", source=source, sequence=sequence)
        for node_id in evidence:
            self._ensure_node(node_id, kind="evidence", source=source, sequence=sequence)

        route_ids: tuple[str, ...] = ()
        if observation.route_id:
            route_ids = (str(observation.route_id),)
            self._ensure_node(route_ids[0], kind="route", source=source, sequence=sequence)
        candidate_ids: tuple[str, ...] = ()
        if observation.candidate_id:
            candidate_ids = (str(observation.candidate_id),)
            self._ensure_node(candidate_ids[0], kind="candidate", source=source, sequence=sequence)

        observed_node_ids = _normalize_ids((*goals, *constraints, *evidence, *route_ids, *candidate_ids))
        self._link_part_of_thought(observed_node_ids, source=source, sequence=sequence)

        for constraint_id in constraints:
            for goal_id in goals:
                self._ensure_edge(
                    constraint_id,
                    goal_id,
                    relation="constrains",
                    source=source,
                    sequence=sequence,
                )
        for route_id in route_ids:
            for goal_id in goals:
                self._ensure_edge(
                    route_id,
                    goal_id,
                    relation="selected_for",
                    source=source,
                    sequence=sequence,
                )
        for candidate_id in candidate_ids:
            for route_id in route_ids:
                self._ensure_edge(
                    candidate_id,
                    route_id,
                    relation="produced_on",
                    source=source,
                    sequence=sequence,
                )
        if candidate_ids:
            for evidence_id in evidence:
                for candidate_id in candidate_ids:
                    self._ensure_edge(
                        evidence_id,
                        candidate_id,
                        relation="selected_for_candidate",
                        source=source,
                        sequence=sequence,
                    )
        else:
            for evidence_id in evidence:
                for goal_id in goals:
                    self._ensure_edge(
                        evidence_id,
                        goal_id,
                        relation="available_for_goal",
                        source=source,
                        sequence=sequence,
                    )

        missing = {
            str(category): _normalize_ids(values)
            for category, values in observation.missing_required_ids.items()
            if _normalize_ids(values)
        }
        transition_payload = {
            "thought_id": self.thought_id,
            "turn_id": self.turn_id,
            "trace_id": self.trace_id,
            "parent_thought_id": self.parent_thought_id,
            "sequence": sequence,
            "stage": observation.stage,
            "event": observation.event,
            "source": source,
            "observed_node_ids": observed_node_ids,
            "missing_required_ids": missing,
            "continuity_ok": observation.continuity_ok,
            "nodes": [self.nodes[key].to_dict() for key in sorted(self.nodes)],
            "edges": [edge.to_dict() for edge in self.edges],
            "shadow_mode": self.shadow_mode,
        }
        transition = CognitiveStateTransition(
            sequence=sequence,
            stage=_clean_token(observation.stage, fallback="unknown_stage"),
            event=_clean_token(observation.event, fallback="observation"),
            source=source,
            observed_node_ids=observed_node_ids,
            missing_required_ids=missing,
            continuity_ok=bool(observation.continuity_ok),
            state_sha256=_sha256_json(transition_payload),
        )
        self.transitions.append(transition)
        if not transition.continuity_ok:
            self.graph_break_count += 1
        return transition

    def append_explicit_node(
        self,
        *,
        node_id: str,
        kind: str,
        source: str,
        stage: str,
        event: str,
    ) -> CognitiveStateTransition:
        """Append an already-opaque explicit runtime node without steering the turn."""

        sequence = len(self.transitions) + 1
        node = self._ensure_node(node_id, kind=kind, source=source, sequence=sequence)
        self._link_part_of_thought((node.node_id,), source=source, sequence=sequence)
        payload = {
            "thought_id": self.thought_id,
            "sequence": sequence,
            "stage": stage,
            "event": event,
            "node_id": node.node_id,
            "kind": node.kind,
            "nodes": [self.nodes[key].to_dict() for key in sorted(self.nodes)],
            "edges": [edge.to_dict() for edge in self.edges],
            "shadow_mode": self.shadow_mode,
        }
        transition = CognitiveStateTransition(
            sequence=sequence,
            stage=_clean_token(stage, fallback="state_update"),
            event=_clean_token(event, fallback="node_observed"),
            source=_clean_token(source, fallback="runtime"),
            observed_node_ids=(node.node_id,),
            continuity_ok=True,
            state_sha256=_sha256_json(payload),
        )
        self.transitions.append(transition)
        return transition

    def supersede_node(
        self,
        *,
        previous_node_id: str,
        replacement_node_id: str,
        replacement_kind: str,
        source: str,
        reason_code: str,
    ) -> CognitiveStateEdge:
        """Explicitly supersede a node; historical state remains auditable."""

        previous = self.nodes.get(str(previous_node_id or "").strip())
        if previous is None:
            raise ValueError("previous_node_id must already exist in cognitive state graph")
        sequence = len(self.transitions) + 1
        replacement = self._ensure_node(
            replacement_node_id,
            kind=replacement_kind,
            source=source,
            sequence=sequence,
        )
        previous.status = "superseded"
        previous.last_observed_sequence = max(previous.last_observed_sequence, sequence)
        self._link_part_of_thought((replacement.node_id,), source=source, sequence=sequence)
        edge = self._ensure_edge(
            replacement.node_id,
            previous.node_id,
            relation="supersedes",
            source=source,
            sequence=sequence,
            reason_code=reason_code,
        )
        payload = {
            "thought_id": self.thought_id,
            "sequence": sequence,
            "previous_node_id": previous.node_id,
            "replacement_node_id": replacement.node_id,
            "reason_code": _clean_token(reason_code, fallback="unspecified"),
            "nodes": [self.nodes[key].to_dict() for key in sorted(self.nodes)],
            "edges": [item.to_dict() for item in self.edges],
            "shadow_mode": self.shadow_mode,
        }
        self.transitions.append(
            CognitiveStateTransition(
                sequence=sequence,
                stage="state_update",
                event="node_superseded",
                source=_clean_token(source, fallback="runtime"),
                observed_node_ids=(previous.node_id, replacement.node_id),
                continuity_ok=True,
                state_sha256=_sha256_json(payload),
            )
        )
        return edge

    def append_epistemic_assessment(
        self,
        assessment: dict[str, Any],
        *,
        source: str = "epistemic_claim_guard",
    ) -> dict[str, Any]:
        """Project one explicit assessment without persisting claim text.

        ``supports`` and ``contradicts`` edges are emitted only when the assessment
        carries explicit source identifiers. Unsupported/inferred classifications
        remain observable claim nodes but never gain a factual support edge.
        """

        payload = dict(assessment or {})
        kind = _clean_token(payload.get("kind"), fallback="unknown_claim")
        status = _clean_token(payload.get("status"), fallback="unsupported")
        matched_text = str(payload.get("matched_text") or "")
        claim_id = "claim:" + _sha256_json({
            "kind": kind,
            "matched_text_sha256": hashlib.sha256(matched_text.encode("utf-8")).hexdigest(),
            "reason": str(payload.get("reason") or "")[:160],
        })
        raw_source_ids = payload.get("source_ids")
        source_ids = _normalize_ids(
            raw_source_ids if isinstance(raw_source_ids, (list, tuple, set)) else ()
        )
        sequence = len(self.transitions) + 1
        self._ensure_node(claim_id, kind="claim", source=source, sequence=sequence)
        evidence_ids: list[str] = []
        for raw_id in source_ids[:32]:
            evidence_id = "evidence:" + hashlib.sha256(raw_id.encode("utf-8")).hexdigest()
            self._ensure_node(evidence_id, kind="evidence", source=source, sequence=sequence)
            evidence_ids.append(evidence_id)
        relation = None
        if evidence_ids and status == "supported":
            relation = "supports"
        elif evidence_ids and status == "contradicted":
            relation = "contradicts"
        if relation:
            for evidence_id in evidence_ids:
                self._ensure_edge(
                    evidence_id,
                    claim_id,
                    relation=relation,
                    source=source,
                    sequence=sequence,
                    reason_code="explicit_epistemic_evidence",
                )
        observed = _normalize_ids((claim_id, *evidence_ids))
        self._link_part_of_thought(observed, source=source, sequence=sequence)
        transition_payload = {
            "thought_id": self.thought_id,
            "sequence": sequence,
            "claim_id": claim_id,
            "status": status,
            "explicit_evidence_count": len(evidence_ids),
            "relation": relation,
            "nodes": [self.nodes[key].to_dict() for key in sorted(self.nodes)],
            "edges": [edge.to_dict() for edge in self.edges],
        }
        self.transitions.append(CognitiveStateTransition(
            sequence=sequence,
            stage="epistemic_boundary",
            event="claim_assessment_observed",
            source=_clean_token(source, fallback="epistemic_claim_guard"),
            observed_node_ids=observed,
            continuity_ok=True,
            state_sha256=_sha256_json(transition_payload),
        ))
        return {
            "claim_id": claim_id,
            "evidence_ids": evidence_ids,
            "relation": relation,
            "explicit_evidence_required": True,
            "private_claim_text_recorded": False,
        }

    @property
    def latest_state_sha256(self) -> str | None:
        return self.transitions[-1].state_sha256 if self.transitions else None

    def active_node_ids(self, kind: str | None = None) -> list[str]:
        kind_token = _clean_token(kind, fallback="") if kind else None
        return [
            node_id
            for node_id, node in sorted(self.nodes.items())
            if node.status == "active" and (kind_token is None or node.kind == kind_token)
        ]

    def summary(self) -> dict[str, Any]:
        return {
            "state_graph_node_count": len(self.nodes),
            "state_graph_edge_count": len(self.edges),
            "state_graph_transition_count": len(self.transitions),
            "state_graph_break_count": self.graph_break_count,
            "state_graph_state_sha256": self.latest_state_sha256,
            "state_graph_shadow_mode": self.shadow_mode,
            "state_graph_control_mode": self.control_mode,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "thought_id": self.thought_id,
            "turn_id": self.turn_id,
            "trace_id": self.trace_id,
            "parent_thought_id": self.parent_thought_id,
            "nodes": [self.nodes[key].to_dict() for key in sorted(self.nodes)],
            "edges": [edge.to_dict() for edge in self.edges],
            "transitions": [transition.to_dict() for transition in self.transitions],
            "node_count": len(self.nodes),
            "edge_count": len(self.edges),
            "transition_count": len(self.transitions),
            "graph_break_count": self.graph_break_count,
            "latest_state_sha256": self.latest_state_sha256,
            "shadow_mode": self.shadow_mode,
            "control_mode": self.control_mode,
            "truth_boundary": self.truth_boundary,
        }
