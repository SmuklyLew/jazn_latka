from __future__ import annotations

from latka_jazn.core.json_types import json_object
from dataclasses import dataclass
from typing import TYPE_CHECKING
from latka_jazn.core.turn_pipeline_state import TurnPipelineState
from latka_jazn.core.turn_pipeline_support import FAST_HEALTH_CHECK_INTENTS

if TYPE_CHECKING:
    from latka_jazn.core.engine import JaznEngine


@dataclass(frozen=True)
class DialogueRouteDecision:
    intent: str
    route: str
    handler: str
    required_components: tuple[str, ...]
    support_semantics: str = "classifier_support_not_probability"


class DialogueRouter:
    """Turn-local dialogue router over the existing runtime services."""

    def __init__(self, engine: JaznEngine) -> None:
        self.engine = engine

    def classify(self, state: TurnPipelineState) -> None:
        engine = self.engine
        state.dialogue_intent_result = engine.dialogue_intent_classifier.classify(
            state.request.text,
            previous_text=str(state.prior_user_text or "") if state.carryover_allowed else None,
            previous_intent=str(state.prior_detected_intent or "") or None,
            previous_route=str(state.prior_runtime_route or "") or None,
            previous_task_state=state.previous_task_state if state.carryover_allowed else None,
            context_age_seconds=state.prior_context_age_seconds,
            carryover_allowed=state.carryover_allowed,
        )
        state.dialogue_intent_report = state.dialogue_intent_result.to_dict()
        engine._record_intent_diagnostic(state.turn_context, state.dialogue_intent_result)
        state.health_check_fast_path = state.dialogue_intent_result.primary_intent in FAST_HEALTH_CHECK_INTENTS
        engine._record_health_check_detection(state.turn_context, state.health_check_fast_path)

    def resolve_and_execute(self, state: TurnPipelineState) -> None:
        self.resolve(state)
        self.execute(state)

    def resolve(self, state: TurnPipelineState) -> DialogueRouteDecision:
        engine = self.engine
        state.decision = engine.conversation_responder.compose(
            state.request.text,
            intent_tags=state.frame.get("intent_tags") or [],
            affect_marker=state.affect_mix.get("state_emoticon") or engine.affect.marker(),
            memory_counts=((state.frame.get("memory_context") or {}).get("counts") if isinstance(state.frame.get("memory_context"), dict) else None),
            memory_context=state.frame.get("memory_context") if isinstance(state.frame.get("memory_context"), dict) else None,
            diagnostics=state.frame.get("fallback_diagnostics") if isinstance(state.frame.get("fallback_diagnostics"), dict) else None,
            polish_understanding=state.frame.get("polish_understanding") if isinstance(state.frame.get("polish_understanding"), dict) else None,
            lexical_semantic_understanding=state.frame.get("lexical_semantic_understanding") if isinstance(state.frame.get("lexical_semantic_understanding"), dict) else None,
        )
        state.decision_dict = state.decision.to_dict()
        state.decision_dict["timestamp_contract"] = state.envelope.cognitive_frame.get("timestamp_contract") or {}
        state.decision_dict["voice_source_contract"] = state.envelope.cognitive_frame.get("voice_source_contract") or engine.voice_source_contract.to_dict()
        state.decision_dict["state_emoticon"] = str(state.affect_mix.get("state_emoticon") or engine.affect.marker() or "").strip()
        state.decision_dict["runtime_rendering_mode"] = state.envelope.cognitive_frame.get("runtime_rendering_mode") or {}
        state.decision_dict["memory_recall_contract_status"] = {
            "items": len((state.envelope.cognitive_frame.get("memory_recall_contract") or {}).get("items") or []),
            "schema_version": "memory_recall_contract_status/v1",
            "truth_boundary": "same liczniki nie wystarczają; pełny payload jest w cognitive_frame.memory_recall_contract",
        }
        state.detected_dialogue_intent, state.route_entry, state.current_dialogue_task_state, state.turn_response_policy = (
            engine._apply_current_dialogue_control(
                text=state.request.text, frame=state.frame, envelope=state.envelope, decision_dict=state.decision_dict,
                dialogue_intent_report=state.dialogue_intent_report, previous_task_state=state.previous_task_state,
                client_context=state.ctx,
            )
        )
        engine._record_route_diagnostic(state.turn_context, state.detected_dialogue_intent, state.route_entry)
        engine._apply_cognitive_control_policy(
            state.envelope, state.frame, state.current_dialogue_task_state, state.turn_response_policy, state.decision_dict)
        state.handler_context = engine._build_route_handler_context(
            decision=state.decision,
            detected_intent=state.detected_dialogue_intent,
            dialogue_intent_report=state.dialogue_intent_report,
            client_context=state.ctx,
            frame=state.frame,
            route_entry=state.route_entry,
            task_state=state.current_dialogue_task_state,
            response_policy=state.turn_response_policy,
            carryover_allowed=state.carryover_allowed,
            prior_user_text=state.prior_user_text,
            prior_detected_intent=state.prior_detected_intent,
            prior_runtime_route=state.prior_runtime_route,
            previous_task_state=state.previous_task_state,
        )
        return DialogueRouteDecision(
            str(state.detected_dialogue_intent), state.route_entry.route,
            state.route_entry.handler_name, tuple(state.route_entry.required_components),
        )

    def execute(self, state: TurnPipelineState) -> None:
        engine = self.engine
        if state.turn_context is not None and state.health_check_fast_path:
            state.turn_context.start_stage("startup_status_collection")
        state.handler_result = engine.route_handler_dispatcher.dispatch(state.route_entry, state.request.text, state.handler_context)
        if state.turn_context is not None and state.health_check_fast_path:
            state.turn_context.complete_stage("startup_status_collection")
        state.dispatch_report = json_object((state.handler_result.data or {}).get("dispatch_report"))
        state.handler_fallback_payload = json_object((state.handler_result.data or {}).get("fallback_decision"))
        engine._record_handler_diagnostic(
            state.turn_context,
            state.dispatch_report,
            state.handler_fallback_payload,
            state.route_entry,
            state.handler_result,
        )
        (
            state.handler_required,
            state.handler_satisfied,
            state.handler_missing,
            state.preserve_handler_body,
        ) = engine._project_handler_result(
            decision=state.decision,
            decision_dict=state.decision_dict,
            handler_result=state.handler_result,
            route_entry=state.route_entry,
        )
