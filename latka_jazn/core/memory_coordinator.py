from __future__ import annotations

from latka_jazn.memory.runtime_persistence import RuntimePersistenceResult
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from latka_jazn.core.turn_execution import TurnExecutionContext
from latka_jazn.core.turn_pipeline_state import FrameBuildState

if TYPE_CHECKING:
    from latka_jazn.core.engine import JaznEngine


@dataclass(frozen=True)
class MemoryProbeRequest:
    text: str
    intent_report: Any
    client_context: dict[str, Any]
    turn_id: str
    trace_id: str
    turn_context: TurnExecutionContext | None = None


@dataclass(frozen=True)
class MemoryProbeResult:
    context: dict[str, Any]
    recall_contract: dict[str, Any]
    observability: dict[str, Any]


class MemoryCoordinator:
    """Turn-local memory coordinator over the existing runtime services."""

    def __init__(self, engine: JaznEngine) -> None:
        self.engine = engine

    def probe(self, request: MemoryProbeRequest) -> MemoryProbeResult:
        context, contract, observability = self.engine._build_turn_memory_recall_evidence(
            request.text, request.intent_report, request.turn_context,
            request.client_context, turn_id=request.turn_id, trace_id=request.trace_id,
        )
        return MemoryProbeResult(context, contract, observability)

    def prepare_context(self, state: FrameBuildState) -> None:
        engine = self.engine
        state.memory_gate_intent_report = state.intent_report or engine.dialogue_intent_classifier.classify(
            state.request.text, previous_text=str((state.request.client_context or {}).get("previous_user_text") or "") or None,
        )
        result = self.probe(MemoryProbeRequest(
            state.request.text, state.memory_gate_intent_report, state.request.client_context,
            state.turn_id, state.trace_id, state.turn_context,
        ))
        state.memory_context = result.context
        state.memory_recall_contract = result.recall_contract
        state.memory_recall_observability = result.observability
        state.raw_chat_status = engine.raw_chat_importer.inspect().to_dict()
        state.tool_use_decision = engine.tool_use_policy.decide(state.request.text).to_dict()
        state.untrusted_source_assessment = engine.untrusted_source_guard.assess(state.request.text).to_dict()
        state.tool_execution_plan = None
        if state.tool_use_decision.get("allowed"):
            state.tool_execution_plan = engine.tool_execution_controller.plan(
                tool_name=str(state.tool_use_decision.get("tool_class") or "external_tool"),
                action="read",
                source_kind="user_document",
                source_content=state.request.text,
                source_origin="current_user_message",
                actor="jazn_runtime",
                reason=str(state.tool_use_decision.get("reason") or "tool_use_policy"),
                write_action=False,
                user_confirmed=False,
            ).to_dict()
        state.cognitive_runtime_plan = engine._build_preliminary_cognitive_runtime_plan(
            state.request.text,
            memory_gate_intent_report=state.memory_gate_intent_report,
            intent_report=state.intent_report,
            client_context=state.request.client_context,
            tool_use_decision=state.tool_use_decision,
            untrusted_source_assessment=state.untrusted_source_assessment,
        )
        state.cognitive_integration = engine._build_integrated_knowledge_and_lexical_context(
            state.request.text, memory_context=state.memory_context, memory_recall_contract=state.memory_recall_contract
        )

    def prepare_candidate(self, state: FrameBuildState) -> None:
        engine = self.engine
        state.session_continuity = engine._stage_turn_write(
            state.turn_context,
            data_type="session_continuity",
            stage="cognitive_frame_context_built",
            commit=lambda: engine.session_continuity.update_index(
                reason="cognitive_frame_context_built",
                source="JaznEngine.build_cognitive_frame",
                extra={"intent_tags": state.intent_tags, "route_hint": state.polish_report.route_hint, "lexical_route_hint": state.lexical_report.route_hint, "nlp_provider": state.nlp_report.provider_summary},
            ),
        )

        state.runtime_candidate = engine.runtime_memory.build_candidate_from_runtime_turn(
            user_text=state.request.text,
            importance=max(state.importance.importance, state.consolidation_plan.weights.total),
            importance_reason=state.importance.reason,
            emotional_tags=[layer.name for layer in state.emotional_profile.layers],
            source=(state.request.client_context or {}).get("client", "chatgpt_cognitive_bridge"),
            raw_excerpt=state.request.text,
            grounding="recognized",
            confidence=0.70,
        )
        state.accepted, state.persistence_reason = engine.runtime_memory.should_persist(state.runtime_candidate)
        state.candidate_fingerprint = engine.runtime_memory.candidate_fingerprint(state.runtime_candidate)
        state.accepted, state.persistence_reason, state.read_only_preview = engine._preview_candidate_persistence_policy(state.accepted, state.persistence_reason, state.request.client_context)
        if state.accepted and state.turn_context is not None:
            state.turn_context.start_stage("candidate_persistence_staging")
            state.write_id = state.turn_context.stage_semantic_write(
                data_type=f"runtime_memory_candidate:{state.runtime_candidate.kind}",
                stage="candidate_persistence_staging",
                commit=lambda candidate=state.runtime_candidate: engine.runtime_memory.persist_candidate(candidate),
            )
            state.turn_context.complete_stage(
                "candidate_persistence_staging",
                status="completed" if state.write_id else "rejected",
                error_code=None if state.write_id else "turn_cancelled",
            )
            state.persistence = RuntimePersistenceResult(
                False,
                state.candidate_fingerprint,
                state.runtime_candidate.kind,
                "turn_local_staged" if state.write_id else "turn_local_staging_rejected",
                [],
            )
        elif state.accepted:
            state.persistence = engine.runtime_memory.persist_candidate(state.runtime_candidate)
        else:
            if state.turn_context is not None:
                state.turn_context.mark_stage("candidate_persistence_staging", status="skipped_preview_read_only" if state.read_only_preview else "skipped_below_threshold")
            state.persistence = RuntimePersistenceResult(False, state.candidate_fingerprint, state.runtime_candidate.kind, state.persistence_reason, [])
