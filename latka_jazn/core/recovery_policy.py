from __future__ import annotations


from typing import TYPE_CHECKING
from latka_jazn.core.turn_pipeline_state import TurnPipelineState
from latka_jazn.core.turn_pipeline_support import _handler_body_can_cross_chatgpt_host_bridge, _model_guided_rejection_disclosure, _speech_truth_gate_required

if TYPE_CHECKING:
    from latka_jazn.core.engine import JaznEngine



def _suppress_internal_handler_evidence(state: TurnPipelineState, engine: JaznEngine) -> None:
    """Do not leak an internal handler evidence draft as user-facing speech."""
    handler_data = getattr(state.handler_result, "data", {})
    if not (
        isinstance(handler_data, dict)
        and handler_data.get("requires_model_language_realization") is True
        and str(state.body or "").strip() == str(state.handler_result.body or "").strip()
    ):
        return
    state.body = "Nie udało mi się przygotować zweryfikowanej odpowiedzi z materiału pamięci w tej turze."
    state.decision_dict["fallback_classification"] = "cannot_answer_directly"
    state.decision_dict["model_generated"] = False
    state.decision_dict["handler_generation_mode"] = "degraded_truth_disclosure"
    state.answer_validation = engine.runtime_answer_validator.validate(
        user_text=state.request.text,
        body=state.body,
        route=str(state.decision_dict.get("route") or ""),
        detected_intent=str(state.detected_dialogue_intent),
    )


class RecoveryPolicy:
    """Turn-local recovery policy over the existing runtime services."""

    def __init__(self, engine: JaznEngine) -> None:
        self.engine = engine

    def resolve(self, state: TurnPipelineState) -> None:
        engine = self.engine
        state.speech_truth_gate_required = _speech_truth_gate_required(state.detected_dialogue_intent, state.handler_result)
        if state.speech_truth_gate_required:
            state.candidate_valid = bool(state.model_synthesis.used and state.first_validation.accepted and not state.template_origin.get("template_id"))
            if not state.candidate_valid and state.model_executor.retry_allowed:
                state.retry_synthesis = engine.model_guided_response_synthesizer.synthesize(
                    adapter=state.speech_adapter or engine.model_adapter,
                    user_text=state.request.text,
                    draft_body=state.decision.body,
                    detected_intent=str(state.detected_dialogue_intent),
                    route=str(state.decision_dict.get("route") or state.route_entry.route),
                    cognitive_frame=state.frame,
                    response_policy={**state.turn_response_policy.to_dict(), "response_plan": state.response_plan.to_dict()},
                    executor_preflight=state.model_executor,
                )
                state.decision_dict["model_guided_retry_count"] = 1
                state.decision_dict["model_guided_retry_synthesis"] = state.retry_synthesis.to_dict()
                engine._record_model_retry_diagnostic(state.turn_context)
                if state.retry_synthesis.used:
                    state.retry_body = engine.guard.enforce(state.retry_synthesis.body.strip())
                    state.retry_template = engine.template_registry.classify_body(
                        state.retry_body, detected_intent=str(state.detected_dialogue_intent)
                    )
                    if state.retry_synthesis.adapter_response:
                        state.retry_validation = engine.runtime_answer_validator.validate_model_candidate(
                            user_text=state.request.text,
                            response={**state.retry_synthesis.adapter_response, "text": state.retry_body},
                            route=str(state.decision_dict.get("route") or ""),
                            detected_intent=str(state.detected_dialogue_intent),
                            template_origin=state.retry_template,
                        )
                    else:
                        state.retry_validation = engine.runtime_answer_validator.validate(
                            user_text=state.request.text,
                            body=state.retry_body,
                            route=str(state.decision_dict.get("route") or ""),
                            detected_intent=str(state.detected_dialogue_intent),
                        )
                    if state.retry_validation.accepted and not state.retry_template.get("template_id"):
                        state.body = state.retry_body
                        state.template_origin = state.retry_template
                        state.first_validation = state.retry_validation
                        state.candidate_valid = True
                        state.decision_dict["model_generated"] = True
                        state.decision_dict["handler_name"] = "ModelGuidedResponseSynthesizer"
                        state.decision_dict["handler_generation_mode"] = "runtime_model_guided"
                        state.decision_dict["source_origin_detail"] = "runtime_model_guided_synthesis_retry"
            if not state.candidate_valid:
                state.host_bridge_accepts_handler = _handler_body_can_cross_chatgpt_host_bridge(
                    adapter_status=state.adapter_status,
                    handler_result=state.handler_result,
                    handler_missing=state.handler_missing,
                    handler_required=state.handler_required,
                    handler_satisfied=state.handler_satisfied,
                    template_origin=state.template_origin,
                    validation=state.first_validation,
                )
                if state.host_bridge_accepts_handler:
                    state.decision_dict["chatgpt_host_visible_bridge"] = {
                        "accepted": True,
                        "reason": "validated_runtime_handler_body_no_local_model_call",
                        "adapter_id": str(state.adapter_status.get("adapter_id") or state.adapter_status.get("name") or "chatgpt_runtime_adapter"),
                        "provider": str(state.adapter_status.get("provider") or "chatgpt_host"),
                        "truth_boundary": (
                            "--chat-gpt uses the ChatGPT host as the visible language channel, but the local "
                            "runtime still owns intent, routing, memory policy, validation and source provenance. "
                            "This pass-through does not claim local model-guided generation."
                        ),
                    }
                    state.decision_dict["fallback_classification"] = "not_fallback"
                    state.decision_dict["requires_host_model"] = False
                    state.decision_dict["runtime_answer_quality"] = "topic_aligned"
                    state.decision_dict["model_generated"] = False
                    state.decision_dict.setdefault(
                        "source_origin_detail",
                        str(getattr(state.handler_result, "source_origin_detail", "") or "chatgpt_host_bridge/validated_runtime_handler_body"),
                    )
                    state.answer_validation = state.first_validation
                else:
                    state.body, state.source_origin_detail, state.runtime_answer_quality, state.model_replied = (
                        _model_guided_rejection_disclosure(state.model_synthesis, state.first_validation)
                    )
                    state.template_origin = engine.template_registry.classify_body(
                        state.body, detected_intent=str(state.detected_dialogue_intent)
                    )
                    state.decision_dict["handler_name"] = "RuntimeTurnTruthGate"
                    state.decision_dict["handler_generation_mode"] = "degraded_truth_disclosure"
                    state.decision_dict["source_origin_detail"] = state.source_origin_detail
                    state.decision_dict["fallback_classification"] = "cannot_answer_directly"
                    state.decision_dict["requires_host_model"] = not state.model_replied
                    state.decision_dict["runtime_answer_quality"] = state.runtime_answer_quality
                    state.decision_dict["model_generated"] = False
                    state.answer_validation = engine.runtime_answer_validator.validate(
                        user_text=state.request.text,
                        body=state.body,
                        route=str(state.decision_dict.get("route") or ""),
                        detected_intent=str(state.detected_dialogue_intent),
                    )
            else:
                state.decision_dict["fallback_classification"] = "not_fallback"
                state.decision_dict["requires_host_model"] = False
                state.decision_dict["runtime_answer_quality"] = "topic_aligned"
                state.answer_validation = state.first_validation
            _suppress_internal_handler_evidence(state, engine)
            state.body, state.continuity_badge_report = engine.continuity_badge_policy.apply(state.body, state.decision_dict)
        else:
            state.synthesis = engine.runtime_response_synthesizer.synthesize(
                user_text=state.request.text, detected_intent=str(state.detected_dialogue_intent), original_body=state.body, route=str(state.decision_dict.get("route") or ""),
                template_origin=state.template_origin if state.template_origin.get("template_id") else None, validation=state.first_validation.to_dict(),
                memory_context=state.frame.get("memory_context") if isinstance(state.frame.get("memory_context"), dict) else {},
            )
            if state.synthesis.should_override and not state.preserve_handler_body:
                state.body = engine.guard.enforce(state.synthesis.body.strip())
                state.decision_dict["route"] = state.synthesis.route
                state.decision_dict["handler_name"] = state.synthesis.handler_name
                state.decision_dict["runtime_answer_quality"] = "mismatch_repaired" if state.first_validation.must_regenerate else "route_registry_dynamic"
                state.decision_dict["repair_synthesis"] = state.synthesis.to_dict()
                state.repair_used = True
            elif state.synthesis.should_override and state.preserve_handler_body:
                state.decision_dict["repair_synthesis_suppressed"] = {
                    "reason": "dedicated_handler_body_satisfied_required_components",
                    "synthesis": state.synthesis.to_dict(),
                    "first_validation": state.first_validation.to_dict(),
                }
                state.decision_dict["runtime_answer_quality"] = "topic_aligned"
            state.body, state.continuity_badge_report = engine.continuity_badge_policy.apply(state.body, state.decision_dict)
            state.answer_validation = engine.runtime_answer_validator.validate(
                user_text=state.request.text, body=state.body, route=str(state.decision_dict.get("route") or ""), detected_intent=str(state.detected_dialogue_intent)
            )
            if state.answer_validation.must_regenerate and state.answer_validation.repair_body and not state.preserve_handler_body:
                state.body = engine.guard.enforce(state.answer_validation.repair_body.strip())
                state.decision_dict["route"] = state.answer_validation.required_repair_route or state.decision_dict.get("route")
                state.decision_dict["runtime_answer_quality"] = "mismatch_repaired"
                state.body, state.continuity_badge_report = engine.continuity_badge_policy.apply(state.body, state.decision_dict)
                state.answer_validation = engine.runtime_answer_validator.validate(
                    user_text=state.request.text, body=state.body, route=str(state.decision_dict.get("route") or ""), detected_intent=str(state.detected_dialogue_intent)
                )
                state.repair_used = True
            elif state.answer_validation.must_regenerate and state.preserve_handler_body:
                state.decision_dict["answer_validation_suppressed"] = {
                    "reason": "dedicated_handler_body_satisfied_required_components",
                    "validation": state.answer_validation.to_dict(),
                }
                state.answer_validation = engine.runtime_answer_validator.validate(
                    user_text=state.request.text, body=state.body, route=str(state.decision_dict.get("route") or ""), detected_intent=str(state.detected_dialogue_intent)
                )
                state.decision_dict["runtime_answer_quality"] = "topic_aligned"

    def resolve_reasoning(self, state: TurnPipelineState) -> None:
        engine = self.engine
        if state.reasoning_decision.decision == "regenerate" and not state.repair_used and not state.decision_dict.get("requires_host_model"):
            state.synthesis = engine.runtime_response_synthesizer.synthesize(
                user_text=state.request.text,
                detected_intent=str(state.detected_dialogue_intent),
                original_body=state.body,
                route=str(state.decision_dict.get("route") or ""),
                template_origin=state.template_origin if state.template_origin.get("template_id") else None,
                validation={"must_regenerate": True, "mismatch_reason": state.reasoning_decision.reason},
                memory_context=state.frame.get("memory_context") if isinstance(state.frame.get("memory_context"), dict) else {},
            )
            if state.synthesis.should_override:
                state.body = engine.guard.enforce(state.synthesis.body.strip())
                state.decision_dict["route"] = state.synthesis.route
                state.decision_dict["handler_name"] = state.synthesis.handler_name
                state.decision_dict["runtime_answer_quality"] = "logic_audit_repaired"
                state.decision_dict["repair_synthesis"] = state.synthesis.to_dict()
                state.repair_used = True
                state.answer_validation = engine.runtime_answer_validator.validate(
                    user_text=state.request.text, body=state.body, route=str(state.decision_dict.get("route") or ""), detected_intent=str(state.detected_dialogue_intent)
                )

    def classify_result(self, state: TurnPipelineState) -> None:
        engine = self.engine
        state.template_origin = engine.template_registry.classify_body(state.body, detected_intent=str(state.detected_dialogue_intent))
        if str(state.decision_dict.get("fallback_classification") or "") in {"", "not_fallback"}:
            if state.repair_used:
                state.decision_dict["fallback_classification"] = "repair_fallback"
            elif state.template_origin.get("template_id"):
                state.decision_dict["fallback_classification"] = "template_fallback"
            elif state.decision_dict.get("model_generated"):
                state.decision_dict["fallback_classification"] = "not_fallback"
            elif str(state.handler_result.body or "").strip():
                state.decision_dict["fallback_classification"] = "rule_handler_response"

    @staticmethod
    def route_failure(*, intent: str, route: str, handler: str, exception: bool = False):
        from latka_jazn.core.turn_diagnostics import FallbackDecision, FallbackKind, TurnStage
        return FallbackDecision.build(
            kind=FallbackKind.RECOVERABLE_FALLBACK,
            origin_stage=TurnStage.HANDLER if exception else TurnStage.ROUTING,
            origin_component="RouteHandlerDispatcher.dispatch",
            reason_code="HANDLER_EXCEPTION" if exception else "ROUTE_HANDLER_UNRESOLVED",
            from_route=route, to_route="fallback", recoverable=True,
            evidence_refs=(intent, handler),
        )
