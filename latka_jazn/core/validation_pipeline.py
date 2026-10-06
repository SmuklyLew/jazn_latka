from __future__ import annotations

from latka_jazn.core.json_types import json_object
from latka_jazn.core.turn_route_trace import TurnRouteTrace
from typing import TYPE_CHECKING
from latka_jazn.core.turn_pipeline_state import TurnPipelineState

if TYPE_CHECKING:
    from latka_jazn.core.engine import JaznEngine


class ValidationPipeline:
    """Turn-local validation pipeline over the existing runtime services."""

    def __init__(self, engine: JaznEngine) -> None:
        self.engine = engine

    def validate_candidate(self, state: TurnPipelineState) -> None:
        engine = self.engine
        state.template_origin = engine.template_registry.classify_body(state.body, detected_intent=str(state.detected_dialogue_intent))
        if state.model_synthesis.used and state.model_synthesis.adapter_response:
            state.first_validation = engine.runtime_answer_validator.validate_model_candidate(
                user_text=state.request.text,
                response=state.model_synthesis.adapter_response,
                route=str(state.decision_dict.get("route") or ""),
                detected_intent=str(state.detected_dialogue_intent),
                template_origin=state.template_origin,
            )
        else:
            state.first_validation = engine.runtime_answer_validator.validate(
                user_text=state.request.text, body=state.body, route=str(state.decision_dict.get("route") or ""), detected_intent=str(state.detected_dialogue_intent)
            )
        engine._record_validation_diagnostic(
            state.turn_context,
            state.first_validation,
            event_type="candidate_validation",
            attempt=0,
        )
        state.repair_used = False

    def assess_reasoning(self, state: TurnPipelineState) -> None:
        engine = self.engine
        if state.turn_context is not None:
            state.turn_context.complete_stage("synthesis")
        state.logic_audit = engine.turn_logic_auditor.audit(
            user_text=state.request.text,
            response_text=state.body,
            detected_intent=str(state.detected_dialogue_intent),
            route=str(state.decision_dict.get("route") or ""),
            handler=str(state.decision_dict.get("handler_name") or state.route_entry.handler_name),
            policy=state.turn_response_policy.to_dict() if state.turn_response_policy is not None else {},
            speech_act=str((state.dialogue_intent_report or {}).get("speech_act") or "unknown"),
            question_object=str((state.dialogue_intent_report or {}).get("question_object") or "unknown"),
        )
        engine._stage_turn_write(
            state.turn_context,
            data_type="turn_logic_audit",
            stage="synthesis_validation",
            commit=lambda: engine.turn_logic_auditor.append(state.logic_audit),
        )
        state.reasoning_decision = engine.reasoning_controller.assess_turn(
            user_text=state.request.text,
            intent=str(state.detected_dialogue_intent),
            route=str(state.decision_dict.get("route") or ""),
            handler_name=str(state.decision_dict.get("handler_name") or state.route_entry.handler_name),
            body=state.body,
            policy=state.turn_response_policy.to_dict() if state.turn_response_policy is not None else {},
            logic_audit=state.logic_audit.to_dict(),
            validation=state.answer_validation.to_dict(),
        )
        state.decision_dict["turn_logic_audit"] = state.logic_audit.to_dict()
        state.decision_dict["reasoning_controller"] = state.reasoning_decision.to_dict()
        state.envelope.cognitive_frame["turn_logic_audit"] = state.logic_audit.to_dict()
        state.envelope.cognitive_frame["reasoning_controller"] = state.reasoning_decision.to_dict()
        state.turn_route_trace = TurnRouteTrace(
            user_text_preview=(state.request.text or "")[:240],
            speech_act=str((state.dialogue_intent_report or {}).get("speech_act") or "unknown"),
            question_object=str((state.dialogue_intent_report or {}).get("question_object") or "unknown"),
            primary_intent_initial=str((state.dialogue_intent_report or {}).get("primary_intent") or "unknown"),
            primary_intent_final=str(state.detected_dialogue_intent),
            secondary_intents=list((state.dialogue_intent_report or {}).get("secondary_intents") or []),
            topic_guard=json_object(state.frame.get("topic_mismatch_guard")),
            turn_logic_audit=state.logic_audit.to_dict(),
            selected_route=str(state.decision_dict.get("route") or state.route_entry.route),
            selected_handler=str(state.decision_dict.get("handler_name") or state.route_entry.handler_name),
            memory_gate=str(((state.frame.get("memory_context") or {}).get("gate") if isinstance(state.frame.get("memory_context"), dict) else None) or "not_needed"),
            startup_status_mode="fast",
            sqlite_health_mode="metadata",
            network_time_used=bool((state.envelope.cognitive_frame.get("timestamp_contract") or {}).get("trusted")),
            deep_audit_used=False,
            runtime_answer_validation=state.answer_validation.to_dict(),
            final_text_source=str(state.decision_dict.get("response_generation_mode") or state.decision_dict.get("handler_generation_mode") or "handler_or_synthesizer"),
        ).to_dict()
        state.decision_dict["turn_route_trace"] = state.turn_route_trace
        state.envelope.cognitive_frame["turn_route_trace"] = state.turn_route_trace

    def record_final_validation(self, state: TurnPipelineState) -> None:
        engine = self.engine
        if isinstance(state.decision_dict.get("turn_route_trace"), dict):
            state.decision_dict["turn_route_trace"]["selected_route"] = str(state.decision_dict.get("route") or state.route_entry.route)
            state.decision_dict["turn_route_trace"]["selected_handler"] = str(state.decision_dict.get("handler_name") or state.route_entry.handler_name)
            state.decision_dict["turn_route_trace"]["runtime_answer_validation"] = state.answer_validation.to_dict()
            state.decision_dict["turn_route_trace"]["final_text_source"] = str(state.decision_dict.get("response_generation_mode") or state.decision_dict.get("handler_generation_mode") or "handler_or_synthesizer")
            state.envelope.cognitive_frame["turn_route_trace"] = state.decision_dict["turn_route_trace"]
        engine._record_validation_diagnostic(
            state.turn_context,
            state.answer_validation,
            event_type="final_validation",
            attempt=1 if state.repair_used else 0,
            repair_used=state.repair_used,
        )

    def complete_validation(self, state: TurnPipelineState) -> None:
        engine = self.engine
        state.decision_dict.setdefault("requires_host_model", False)
        state.decision_dict["final_answer_validation"] = state.answer_validation.to_dict()
        # Origin truth is computed only after runtime provenance and the final
        # candidate body exist. A bridge's accepted flag alone is not evidence.
        state.decision_dict.pop("origin_truth_valid", None)
        if isinstance(state.decision_dict.get("turn_route_trace"), dict):
            state.decision_dict["turn_route_trace"].update({
                "fallback_classification": state.decision_dict.get("fallback_classification"),
                "source_origin_detail": state.decision_dict.get("source_origin_detail"),
                "can_generate_model_guided_speech": state.can_generate_model_guided_speech,
                "requires_host_model": bool(state.decision_dict.get("requires_host_model")),
                "retry_count": int(state.decision_dict.get("model_guided_retry_count") or 0),
            })
            state.envelope.cognitive_frame["turn_route_trace"] = state.decision_dict["turn_route_trace"]
        engine._record_final_turn_diagnostics(
            turn_context=state.turn_context,
            decision_dict=state.decision_dict,
            route_entry=state.route_entry,
            answer_validation=state.answer_validation,
            detected_dialogue_intent=state.detected_dialogue_intent,
            handler_required=state.handler_required,
            handler_satisfied=state.handler_satisfied,
            handler_missing=state.handler_missing,
            dispatch_report=state.dispatch_report,
            envelope=state.envelope,
        )
