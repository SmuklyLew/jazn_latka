from __future__ import annotations

import copy
from dataclasses import asdict, dataclass, field
import hashlib
import json
import uuid
from typing import Any

from latka_jazn.core.cognitive_lineage import (
    CognitiveLineage,
    constraint_references_from_policy,
    evidence_references_from_memory_contract,
    evidence_references_from_selected_sources,
    resolve_parent_thought_id,
)
from latka_jazn.core.cognitive_state_graph import CognitiveStateGraph
from latka_jazn.core.full_canon_model_context import (
    build_full_canon_model_context,
    build_host_generation_contract,
)

SCHEMA_VERSION = "cognitive_turn_envelope/v1"
TRACE_SCHEMA_VERSION = "turn_trace/v1"


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


@dataclass(slots=True)
class TurnTrace:
    """One turn identity carried through runtime, cognitive frame and final text."""

    turn_id: str
    trace_id: str
    timestamp_header: str
    timezone: str
    runtime_mode: str
    client: str
    lifecycle: str
    schema_version: str = TRACE_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class CognitiveTurnEnvelope:
    """One integration envelope for state, canon, memory and visible response."""

    trace: TurnTrace
    runtime_version: str
    user_text: str
    cognitive_frame: dict[str, Any]
    cognitive_lineage: CognitiveLineage
    cognitive_state_graph: CognitiveStateGraph
    client_context: dict[str, Any] = field(default_factory=dict)
    affect_mix: dict[str, Any] = field(default_factory=dict)
    dialogue_state: dict[str, Any] = field(default_factory=dict)
    conversation_decision: dict[str, Any] = field(default_factory=dict)
    runtime_turn_contract: dict[str, Any] = field(default_factory=dict)
    final_response_contract: dict[str, Any] = field(default_factory=dict)
    final_visible_text: str | None = None
    schema_version: str = SCHEMA_VERSION

    @classmethod
    def from_cognitive_frame(
        cls,
        frame: dict[str, Any],
        *,
        user_text: str,
        client_context: dict[str, Any] | None = None,
        runtime_mode: str = "process_turn",
    ) -> "CognitiveTurnEnvelope":
        client_context = dict(client_context or {})
        trace_packet = dict(frame.get("turn_trace") or {})
        turn_id = str(trace_packet.get("turn_id") or frame.get("turn_id") or uuid.uuid4())
        trace_id = str(trace_packet.get("trace_id") or frame.get("trace_id") or uuid.uuid4())
        timestamp_header = str(trace_packet.get("timestamp_header") or frame.get("timestamp") or "")
        timezone = str(trace_packet.get("timezone") or frame.get("response_format", {}).get("timezone") or "Europe/Warsaw")
        client = str(trace_packet.get("client") or client_context.get("client") or frame.get("client_context", {}).get("client") or "runtime")
        lifecycle = str(trace_packet.get("lifecycle") or client_context.get("lifecycle") or frame.get("client_context", {}).get("lifecycle") or "one_shot")
        trace = TurnTrace(
            turn_id=turn_id,
            trace_id=trace_id,
            timestamp_header=timestamp_header,
            timezone=timezone,
            runtime_mode=runtime_mode,
            client=client,
            lifecycle=lifecycle,
        )
        copied = copy.deepcopy(frame)
        copied["turn_trace"] = trace.to_dict()
        copied["turn_id"] = turn_id
        copied["trace_id"] = trace_id
        lineage = CognitiveLineage.create(
            turn_id=turn_id,
            trace_id=trace_id,
            parent_thought_id=resolve_parent_thought_id(client_context),
        )
        state_graph = CognitiveStateGraph.create(lineage)
        memory_contract = copied.get("memory_recall_contract")
        evidence_refs = evidence_references_from_memory_contract(
            memory_contract if isinstance(memory_contract, dict) else {}
        )
        if evidence_refs:
            evidence_observation = lineage.observe(
                stage="memory_recall_contract",
                event="evidence_available",
                source="cognitive_turn_envelope",
                evidence_refs=evidence_refs,
                anchor_categories=("evidence",),
            )
            state_graph.observe_lineage_observation(evidence_observation)
        copied["cognitive_lineage"] = lineage.to_dict()
        copied["cognitive_state_graph"] = state_graph.to_dict()
        full_canon = build_full_canon_model_context(copied)
        copied["full_canon_model_context"] = full_canon
        copied["host_generation_contract"] = build_host_generation_contract(full_canon)
        copied["full_canon_sha256"] = full_canon.get("immutable_canon_sha256")
        return cls(
            trace=trace,
            runtime_version=str(frame.get("runtime_version") or "unknown"),
            user_text=user_text,
            cognitive_frame=copied,
            cognitive_lineage=lineage,
            cognitive_state_graph=state_graph,
            client_context=client_context,
        )

    def attach_affect_mix(self, affect_mix: dict[str, Any]) -> None:
        self.affect_mix = dict(affect_mix or {})
        self.cognitive_frame["turn_affect_mix"] = self.affect_mix
        self._refresh_full_canon_dynamic_context()

    def attach_dialogue_state(self, dialogue_state: dict[str, Any]) -> None:
        self.dialogue_state = dict(dialogue_state or {})
        self.cognitive_frame["dialogue_state"] = self.dialogue_state
        self._refresh_full_canon_dynamic_context()

    def attach_conversation_decision(self, decision: dict[str, Any]) -> None:
        self.conversation_decision = dict(decision or {})
        self._observe_decision_lineage(self.conversation_decision)
        self._sync_lineage_into_route_trace(self.conversation_decision)
        self.cognitive_frame["conversation_decision"] = self.conversation_decision

    def attach_final_response_contract(self, contract: dict[str, Any], final_visible_text: str) -> None:
        self.final_response_contract = dict(contract or {})
        self.final_visible_text = final_visible_text
        self._observe_finalization_lineage()
        self._sync_lineage_into_route_trace(self.conversation_decision)
        self.cognitive_frame["final_response_contract"] = self.final_response_contract
        self.cognitive_frame["final_visible_reply_sha256"] = hashlib.sha256(final_visible_text.encode("utf-8")).hexdigest()

    def attach_runtime_turn_contract(self, contract: dict[str, Any]) -> None:
        self.runtime_turn_contract = dict(contract or {})
        self.cognitive_frame["runtime_turn_contract"] = self.runtime_turn_contract

    def _decision_lineage_inputs(
        self, decision: dict[str, Any]
    ) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...], str | None, str | None]:
        task_state = decision.get("dialogue_task_state")
        if not isinstance(task_state, dict):
            task_state = self.cognitive_frame.get("dialogue_task_state")
        task_state = task_state if isinstance(task_state, dict) else {}

        policy = decision.get("turn_response_policy")
        if not isinstance(policy, dict):
            policy = self.cognitive_frame.get("turn_response_policy")
        policy = policy if isinstance(policy, dict) else {}

        goal = str(task_state.get("active_goal") or "").strip()
        goal_refs = (goal,) if goal else ()
        constraint_refs = constraint_references_from_policy(policy)

        synthesis = decision.get("model_guided_synthesis")
        if not isinstance(synthesis, dict):
            synthesis = decision.get("model_guided_retry_synthesis")
        synthesis = synthesis if isinstance(synthesis, dict) else {}
        sources = synthesis.get("sources")
        evidence_refs = evidence_references_from_selected_sources(
            sources if isinstance(sources, list) else []
        )
        if not evidence_refs:
            memory_contract = self.cognitive_frame.get("memory_recall_contract")
            evidence_refs = evidence_references_from_memory_contract(
                memory_contract if isinstance(memory_contract, dict) else {}
            )

        route = str(decision.get("route") or "").strip() or None
        validation = synthesis.get("candidate_validation")
        candidate = None
        if isinstance(validation, dict):
            candidate = str(validation.get("candidate_id") or "").strip() or None
        return goal_refs, constraint_refs, evidence_refs, route, candidate

    def _observe_decision_lineage(self, decision: dict[str, Any]) -> None:
        goal_refs, constraint_refs, evidence_refs, route, candidate = self._decision_lineage_inputs(decision)
        observed_categories = {
            "goal": bool(goal_refs),
            "constraint": bool(constraint_refs),
            "evidence": bool(evidence_refs),
        }
        anchor_categories = tuple(
            category
            for category, present in observed_categories.items()
            if present and not getattr(self.cognitive_lineage, f"anchored_{category}_ids")
        )
        expect_categories = tuple(
            category
            for category, present in observed_categories.items()
            if present and getattr(self.cognitive_lineage, f"anchored_{category}_ids")
        )
        self.observe_cognitive_lineage(
            stage="conversation_decision",
            event="runtime_decision_observed",
            source="cognitive_turn_envelope",
            goal_refs=goal_refs,
            constraint_refs=constraint_refs,
            evidence_refs=evidence_refs,
            route_ref=route,
            candidate_ref=candidate,
            anchor_categories=anchor_categories,
            expect_categories=expect_categories,
        )

    def _observe_finalization_lineage(self) -> None:
        goal_refs, constraint_refs, evidence_refs, route, candidate = self._decision_lineage_inputs(
            self.conversation_decision
        )
        expected = tuple(
            category
            for category in ("goal", "constraint", "evidence")
            if getattr(self.cognitive_lineage, f"anchored_{category}_ids")
        )
        self.observe_cognitive_lineage(
            stage="final_response_contract",
            event="finalization_observed",
            source="cognitive_turn_envelope",
            goal_refs=goal_refs,
            constraint_refs=constraint_refs,
            evidence_refs=evidence_refs,
            route_ref=route,
            candidate_ref=candidate,
            expect_categories=expected,
        )

    def _sync_lineage_into_route_trace(self, decision: dict[str, Any]) -> None:
        route_trace = decision.get("turn_route_trace")
        if not isinstance(route_trace, dict):
            return
        route_trace = dict(route_trace)
        route_trace.update(self.cognitive_lineage.summary())
        route_trace.update(self.cognitive_state_graph.summary())
        decision["turn_route_trace"] = route_trace
        self.cognitive_frame["turn_route_trace"] = dict(route_trace)

    def observe_cognitive_lineage(
        self,
        *,
        stage: str,
        event: str,
        source: str,
        goal_refs: list[str] | tuple[str, ...] | None = None,
        constraint_refs: list[str] | tuple[str, ...] | None = None,
        evidence_refs: list[str] | tuple[str, ...] | None = None,
        route_ref: str | None = None,
        candidate_ref: str | None = None,
        anchor_categories: list[str] | tuple[str, ...] | None = None,
        expect_categories: list[str] | tuple[str, ...] | None = None,
    ) -> dict[str, Any]:
        """Append one shadow-only semantic hand-off observation.

        The observation is deliberately excluded from control decisions. It is
        copied into the envelope only after runtime modules have produced their
        own outputs, so lineage can diagnose hand-off loss without steering the
        same turn it measures.
        """

        observation = self.cognitive_lineage.observe(
            stage=stage,
            event=event,
            source=source,
            goal_refs=goal_refs,
            constraint_refs=constraint_refs,
            evidence_refs=evidence_refs,
            route_ref=route_ref,
            candidate_ref=candidate_ref,
            anchor_categories=anchor_categories,
            expect_categories=expect_categories,
        )
        self.cognitive_state_graph.observe_lineage_observation(observation)
        self.cognitive_frame["cognitive_lineage"] = self.cognitive_lineage.to_dict()
        self.cognitive_frame["cognitive_state_graph"] = self.cognitive_state_graph.to_dict()
        return observation.to_dict()

    def refresh_finalization_timestamp(
        self,
        *,
        timestamp_header: str,
        timestamp_contract: dict[str, Any],
    ) -> dict[str, Any]:
        """Refresh the visible timestamp after long synthesis without losing turn-start time."""

        header = str(timestamp_header or "").strip()
        contract = copy.deepcopy(dict(timestamp_contract or {}))
        if not header:
            raise ValueError("timestamp_header is required")
        missing = [
            name
            for name in ("sample_iso", "source", "trusted")
            if name not in contract or contract.get(name) in (None, "")
        ]
        if missing:
            raise ValueError(
                "timestamp_contract missing required fields: " + ", ".join(missing)
            )

        started_header = str(
            self.cognitive_frame.get("turn_started_timestamp_header")
            or self.trace.timestamp_header
            or ""
        )
        started_contract = self.cognitive_frame.get("turn_started_timestamp_contract")
        if not isinstance(started_contract, dict):
            previous_contract = self.cognitive_frame.get("timestamp_contract")
            started_contract = (
                copy.deepcopy(previous_contract)
                if isinstance(previous_contract, dict)
                else {}
            )

        self.cognitive_frame["turn_started_timestamp_header"] = started_header
        self.cognitive_frame["turn_started_timestamp_contract"] = copy.deepcopy(
            started_contract
        )
        self.cognitive_frame["finalization_timestamp_header"] = header
        self.cognitive_frame["finalization_timestamp_contract"] = copy.deepcopy(
            contract
        )
        self.cognitive_frame["timestamp"] = header
        self.cognitive_frame["timestamp_contract"] = copy.deepcopy(contract)

        self.trace.timestamp_header = header
        self.cognitive_frame["turn_trace"] = self.trace.to_dict()

        response_format = dict(self.cognitive_frame.get("response_format") or {})
        response_format["timestamp_prefix"] = header
        response_format["current_timestamp"] = header
        response_format["example_start"] = f"{header} "
        response_format.setdefault("timezone", self.trace.timezone)
        self.cognitive_frame["response_format"] = response_format

        if self.conversation_decision:
            decision = dict(self.conversation_decision)
            decision.setdefault(
                "turn_started_timestamp_header",
                started_header,
            )
            decision.setdefault(
                "turn_started_timestamp_contract",
                copy.deepcopy(started_contract),
            )
            decision["finalization_timestamp_header"] = header
            decision["finalization_timestamp_contract"] = copy.deepcopy(contract)
            decision["timestamp_contract"] = copy.deepcopy(contract)
            self.attach_conversation_decision(decision)

        self._refresh_full_canon_dynamic_context()
        return {
            "turn_started_timestamp_header": started_header,
            "turn_started_timestamp_contract": copy.deepcopy(started_contract),
            "finalization_timestamp_header": header,
            "finalization_timestamp_contract": copy.deepcopy(contract),
        }

    def _refresh_full_canon_dynamic_context(self) -> None:
        full_canon = build_full_canon_model_context(self.cognitive_frame)
        self.cognitive_frame["full_canon_model_context"] = full_canon
        self.cognitive_frame["host_generation_contract"] = build_host_generation_contract(full_canon)
        self.cognitive_frame["full_canon_sha256"] = full_canon.get("immutable_canon_sha256")

    def to_dict(self) -> dict[str, Any]:
        full_canon = self.cognitive_frame.get("full_canon_model_context")
        if not isinstance(full_canon, dict):
            self._refresh_full_canon_dynamic_context()
            full_canon = self.cognitive_frame.get("full_canon_model_context") or {}
        host_contract = self.cognitive_frame.get("host_generation_contract")
        if not isinstance(host_contract, dict):
            host_contract = build_host_generation_contract(full_canon)
            self.cognitive_frame["host_generation_contract"] = host_contract
        data = {
            "schema_version": self.schema_version,
            "runtime_version": self.runtime_version,
            "trace": self.trace.to_dict(),
            "user_text": self.user_text,
            "client_context": self.client_context,
            "cognitive_lineage": self.cognitive_lineage.to_dict(),
            "cognitive_state_graph": self.cognitive_state_graph.to_dict(),
            "affect_mix": self.affect_mix,
            "dialogue_state": self.dialogue_state,
            "conversation_decision": self.conversation_decision,
            "runtime_turn_contract": self.runtime_turn_contract,
            "final_response_contract": self.final_response_contract,
            "final_visible_text": self.final_visible_text,
            "full_canon_model_context": full_canon,
            "full_canon_sha256": full_canon.get("immutable_canon_sha256"),
            "host_generation_contract": host_contract,
            "cognitive_frame": self.cognitive_frame,
            "payload_sha256": _sha256_json({
                "trace": self.trace.to_dict(),
                "user_text": self.user_text,
                "cognitive_frame": self.cognitive_frame,
                "final_visible_text": self.final_visible_text,
            }),
            "truth_boundary": (
                "Koperta tury spina realne wywołanie runtime, pełny kanon, cognitive-frame i finalną odpowiedź. "
                "Nie oznacza stałego procesu w tle ani nie przenosi źródła tożsamości do hosta."
            ),
        }
        return data
