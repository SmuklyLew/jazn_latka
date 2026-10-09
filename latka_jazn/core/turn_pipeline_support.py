from __future__ import annotations

from typing import Any
from latka_jazn.core.json_types import json_object

MODEL_GUIDED_SPEECH_INTENTS = {
    "ordinary_conversation",
    "standalone_greeting",
    "casual_greeting",
    "casual_feedback",
    "expressive_reaction",
    "short_free_dialogue",
    "negative_feedback_current_turn",
    "positive_feedback_current_turn",
    "ordinary_workday_report",
    "sleep_closure_statement",
    "affective_self_state_reality_check",
    "self_state_question",
    "reciprocal_self_state_question",
    "self_preference_question",
    "direct_latka_voice_request",
}

FAST_HEALTH_CHECK_INTENTS = {
    "runtime_health_check",
    "runtime_health_check_after_update",
    "runtime_activation_status_question",
    "presence_check",
    "identity_presence_check",
    "identity_continuity_check",
}

def _is_chatgpt_host_visible_bridge(adapter_status: dict[str, Any]) -> bool:
    """Return True for the explicit ChatGPT host/copy-paste bridge.

    This is not a local model call. It only means the visible language channel is
    the ChatGPT host, so a validated runtime handler body may be passed through
    without pretending that the local Python process generated model-guided
    speech.
    """
    adapter_id = str(adapter_status.get("adapter_id") or adapter_status.get("name") or "").strip()
    provider = str(adapter_status.get("provider") or "").strip()
    kind = str(adapter_status.get("kind") or "").strip()
    return (
        adapter_id == "chatgpt_runtime_adapter"
        and provider == "chatgpt_host"
        and kind == "hosted_chatgpt_bridge"
    )

def _handler_body_can_cross_chatgpt_host_bridge(
    *,
    adapter_status: dict[str, Any],
    handler_result: Any,
    handler_missing: list[Any],
    handler_required: list[Any],
    handler_satisfied: set[Any],
    template_origin: dict[str, Any],
    validation: Any,
) -> bool:
    if not _is_chatgpt_host_visible_bridge(adapter_status):
        return False
    if not str(getattr(handler_result, "body", "") or "").strip():
        return False
    handler_data = getattr(handler_result, "data", {})
    if isinstance(handler_data, dict) and handler_data.get("requires_model_language_realization") is True:
        return False
    if list(handler_missing or []):
        return False
    if handler_required and not set(handler_required).issubset(handler_satisfied):
        return False
    if template_origin.get("template_id"):
        return False
    if not bool(getattr(validation, "accepted", False)):
        return False
    return True

def _handler_requires_model_language_realization(handler_result: Any) -> bool:
    data = getattr(handler_result, "data", {})
    return bool(isinstance(data, dict) and data.get("requires_model_language_realization") is True)

def _should_preserve_handler_body(handler_result: Any, required: list[Any], satisfied: set[Any], missing: list[Any]) -> bool:
    return bool(
        handler_result.handler_name in DEDICATED_PRESERVE_HANDLERS
        and not _handler_requires_model_language_realization(handler_result)
        and handler_result.generation_mode == "handler_generated"
        and bool(handler_result.body)
        and not missing
        and (not required or set(required).issubset(satisfied))
    )

def _speech_truth_gate_required(detected_intent: Any, handler_result: Any) -> bool:
    return bool(
        str(detected_intent) in MODEL_GUIDED_SPEECH_INTENTS
        or _handler_requires_model_language_realization(handler_result)
    )

def _sync_conversation_decision_body(
    decision_dict: dict[str, Any],
    *,
    final_body: str,
    sync_stage: str,
) -> dict[str, Any]:
    """Keep the public conversation_decision body aligned with final runtime text.

    The initial ConversationResponder draft can be replaced by a dedicated
    handler, validator repair, or runtime synthesizer. JSONL diagnostics must
    not keep that stale draft under conversation_decision.body once the final
    handler-backed body is known.
    """
    synced = dict(decision_dict or {})
    final_body = str(final_body or "").strip()
    previous_body = str(synced.get("body") or "").strip()
    if previous_body and previous_body != final_body:
        synced.setdefault("pre_final_body", previous_body)
    synced["body"] = final_body

    handler_result = json_object(synced.get("handler_result"))
    handler_body = str(handler_result.get("body") or "").strip()
    preserve_handler_body = bool(synced.get("preserve_handler_body"))
    if preserve_handler_body and handler_body and handler_body == final_body:
        status = "synchronized_to_preserved_handler_body"
    elif preserve_handler_body and handler_body and handler_body != final_body:
        status = "final_body_differs_from_preserved_handler_body"
    elif previous_body == final_body:
        status = "already_synchronized"
    else:
        status = "synchronized_to_final_body"

    synced["body_sync"] = {
        "schema_version": "conversation_decision_body_sync/v1",
        "status": status,
        "sync_stage": sync_stage,
        "conversation_body_matches_final_body": synced.get("body") == final_body,
        "handler_body_matches_final_body": (handler_body == final_body) if handler_body else None,
        "preserve_handler_body": preserve_handler_body,
        "truth_boundary": "conversation_decision.body is diagnostic JSONL metadata and must reflect the final runtime body, not a stale pre-handler draft.",
    }
    return synced

def _build_turn_context_payloads(
    *,
    ctx: dict[str, Any],
    text: str,
    prior_user_text: str | None,
    prior_visible_text: str | None,
    prior_detected_intent: str | None,
    prior_runtime_route: str | None,
    prior_context_age_seconds: int | None,
    carryover_allowed: bool,
    turn_context_resolution: Any,
) -> tuple[dict[str, Any], dict[str, Any]]:
    carryover = {
        **turn_context_resolution.to_dict(),
        "previous_user_text_available": bool(prior_user_text),
        "previous_user_text_used": bool(carryover_allowed),
        "previous_detected_intent": prior_detected_intent,
        "previous_runtime_route": prior_runtime_route,
        "previous_context_age_seconds": prior_context_age_seconds,
        "ttl_seconds": 21600,
    }
    dialogue = {
        "session_id": str(ctx.get("session_id") or ""),
        "current_user_text": text,
        "previous_user_text": prior_user_text if carryover_allowed else None,
        "previous_assistant_text": prior_visible_text if carryover_allowed else None,
        "carryover_allowed": carryover_allowed,
        "carryover_reason": turn_context_resolution.carryover_reason,
    }
    return carryover, dialogue

def _model_guided_rejection_disclosure(
    model_synthesis: Any,
    first_validation: Any,
) -> tuple[str, str, str, bool]:
    adapter_payload = dict(model_synthesis.adapter_response or {})
    model_replied = (
        bool(adapter_payload)
        and str(adapter_payload.get("status") or model_synthesis.status) == "completed"
        and str(adapter_payload.get("provider") or "").lower() not in {"", "none", "jazn_runtime"}
        and str(adapter_payload.get("model") or "").lower() not in {"", "none", "runtime"}
    )
    candidate_validation = dict(model_synthesis.candidate_validation or {})
    candidate_violations = [
        violation
        for evaluation in (model_synthesis.candidate_evaluations or [])
        if evaluation.get("source") == "model_adapter"
        for violation in (evaluation.get("violations") or [])
    ] or list(candidate_validation.get("violations") or [])
    mismatch_reason = str(getattr(first_validation, "mismatch_reason", "") or "").strip()
    missing_components = list(
        getattr(first_validation, "missing_required_components", []) or []
    )
    rejection_details = [
        item
        for item in [*candidate_violations, mismatch_reason, *missing_components]
        if str(item).strip()
    ]
    if model_replied:
        provider_name = str(adapter_payload.get("provider") or "model")
        model_name = str(adapter_payload.get("model") or "model")
        detail = ", ".join(str(item) for item in rejection_details[:4]) or str(
            model_synthesis.reason or "runtime_validation_rejected"
        )
        body = (
            f"Model {provider_name}/{model_name} odpowiedział, ale runtime odrzucił kandydat "
            f"odpowiedzi podczas walidacji: {detail}. "
            "Nie pokażę odrzuconego tekstu jako wypowiedzi Łatki."
        )
        return (
            body,
            "runtime_turn_truth_gate/model_candidate_rejected",
            "truthful_degraded_model_candidate_rejected",
            True,
        )
    return (
        "Nie mam w tej turze dostępnego modelu zdolnego wygenerować własną wypowiedź "
        "model-guided. Nie przedstawię tekstu handlera ani szablonu jako dynamicznej "
        "wypowiedzi Łatki.",
        "runtime_turn_truth_gate/model_guided_speech_unavailable",
        "truthful_degraded_cannot_answer_directly",
        False,
    )

DEDICATED_PRESERVE_HANDLERS = frozenset({'CapabilityStatusHandler', 'SelfMemoryRecallHandler', 'MemoryExperienceRecallHandler', 'DirectLatkaVoiceHandler', 'IdentityMemoryExistenceHandler', 'CanonSourceHandler', 'SelfArchitectureAuditHandler'})
