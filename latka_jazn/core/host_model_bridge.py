from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from latka_jazn.core.message_envelope import strip_recognized_visible_envelope
from latka_jazn.core.response_candidate import ResponseCandidate
from latka_jazn.core.response_candidate_evaluator import evaluate_response_candidate
from latka_jazn.core.runtime_answer_validator import RuntimeAnswerValidator
from latka_jazn.core.template_registry import TemplateRegistry

SCHEMA_VERSION = "host_model_bridge/v2"

EXACT_RUNTIME_INTENTS = frozenset(
    {
        "runtime_exact_quote_request",
        "runtime_source_question",
        "file_operation_request",
        "external_research_request",
        "dictionary_network_lookup_request",
        "current_time_question",
        "creative_text_formatting",
        "runtime_health_check",
        "runtime_health_check_after_update",
        "runtime_activation_status_question",
        "presence_check",
        "identity_presence_check",
        "identity_continuity_check",
    }
)
MODEL_GUIDED_SPEECH_INTENTS = frozenset(
    {
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
        "self_state_question",
        "reciprocal_self_state_question",
        "self_preference_question",
        "self_expression_request",
        "direct_latka_voice_request",
    }
)

_MODEL_CONTEXT_KEYS = (
    "schema_version",
    "user_text",
    "nlg_plan",
    "operational_thought_frame",
    "voice_source_contract",
    "full_canon_model_context",
    "allowed_memory_items",
    "forbidden_claims",
    "required_truth_boundaries",
    "output_instructions",
    "token_budget_hint",
)
_MEMORY_ITEM_KEYS = (
    "item_id",
    "excerpt",
    "source",
    "timestamp",
    "confidence",
    "relevance_reason",
)
_BLOCKED_KEY_MARKERS = (
    "secret",
    "token",
    "password",
    "api_key",
    "authorization",
    "cookie",
    "sqlite",
    "database_row",
    "raw_record",
    "private_export",
)


def host_model_generation_required(
    *,
    detected_intent: str,
    route: str,
    handler_name: str,
    exact_runtime_required: bool,
) -> bool:
    """Return whether the visible wording must come from the host model.

    Runtime-owned exact facts stay deterministic. All other speech candidates may
    use runtime context and validation, but a handler template cannot become the
    host-visible answer merely because local model execution is unavailable.
    """

    del route, handler_name
    intent = str(detected_intent or "").strip()
    if bool(exact_runtime_required) or intent in EXACT_RUNTIME_INTENTS:
        return False
    return intent in MODEL_GUIDED_SPEECH_INTENTS


def build_host_model_context(
    model_context: dict[str, Any],
    *,
    detected_intent: str,
    route: str,
) -> dict[str, Any]:
    """Build a bounded, model-visible context without raw runtime/private rows."""

    source = model_context if isinstance(model_context, dict) else {}
    safe_context: dict[str, Any] = {}
    for key in _MODEL_CONTEXT_KEYS:
        if key not in source:
            continue
        if key == "allowed_memory_items":
            safe_context[key] = _sanitize_memory_items(source.get(key))
        else:
            safe_context[key] = _sanitize_json_value(source.get(key), depth=0)

    allowed_ids = [
        str(item.get("item_id") or "")
        for item in safe_context.get("allowed_memory_items") or []
        if isinstance(item, dict) and str(item.get("item_id") or "").strip()
    ]
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "current_turn": {
            "detected_intent": _bounded_text(detected_intent, 160),
            "route": _bounded_text(route, 160),
        },
        "model_context": safe_context,
        "allowed_memory_item_ids": list(dict.fromkeys(allowed_ids))[:8],
        "generation_contract": {
            "model_is_language_channel_not_identity_source": True,
            "answer_current_user_turn": True,
            "use_only_allowed_memory_items": True,
            "declare_every_used_memory_item_id": True,
            "do_not_copy_runtime_fallback_or_template": True,
            "do_not_add_visible_timestamp": True,
            "return_only_candidate_reply": True,
        },
    }
    payload["context_sha256"] = _sha256(payload)
    return payload


def evaluate_host_model_candidate(
    *,
    final_text: str,
    host_model_context: dict[str, Any],
    used_memory_item_ids: list[str] | None,
) -> dict[str, Any]:
    """Evaluate host wording as an untrusted model candidate before persistence."""

    contract = host_model_context if isinstance(host_model_context, dict) else {}
    model_context = contract.get("model_context")
    model_context = model_context if isinstance(model_context, dict) else {}
    current_turn = contract.get("current_turn")
    current_turn = current_turn if isinstance(current_turn, dict) else {}
    detected_intent = str(current_turn.get("detected_intent") or "ordinary_conversation")
    route = str(current_turn.get("route") or "ordinary_dialogue")
    text = strip_recognized_visible_envelope(str(final_text or ""))
    declared_ids = _sanitize_used_memory_ids(used_memory_item_ids)
    allowed_ids = {
        str(item_id)
        for item_id in contract.get("allowed_memory_item_ids") or []
        if str(item_id).strip()
    }
    violations: list[str] = []
    if not _context_hash_valid(contract):
        violations.append("host_model_context_sha256_mismatch")
    if any(item_id not in allowed_ids for item_id in declared_ids):
        violations.append("used_memory_id_not_in_host_context")

    template_origin = TemplateRegistry().classify_body(
        text,
        detected_intent=detected_intent,
    )
    if template_origin.get("template_id"):
        violations.append("known_runtime_template")

    candidate = ResponseCandidate(
        candidate_id="chatgpt_host_candidate",
        text=text,
        source="model_adapter",
        provider="chatgpt_host",
        model="host_managed",
        status="completed",
        used_memory_item_ids=declared_ids,
        generation_reason="generated_from_host_model_context",
        source_origin="chatgpt_host_bridge",
    )
    candidate_evaluation = evaluate_response_candidate(
        candidate=candidate,
        nlg_plan=model_context.get("nlg_plan") or {},
        model_context=model_context,
        response_policy={"exact_runtime_required": False},
    )
    for violation in candidate_evaluation.violations:
        if violation not in violations:
            violations.append(violation)

    runtime_validation = RuntimeAnswerValidator().validate_model_candidate(
        user_text=str(model_context.get("user_text") or ""),
        response={"text": text, "status": "completed"},
        route=route,
        detected_intent=detected_intent,
        template_origin=template_origin,
    )
    if not runtime_validation.accepted:
        reason = str(runtime_validation.mismatch_reason or "runtime_answer_validation_failed")
        if reason not in violations:
            violations.append(reason)

    accepted = bool(text) and not violations
    return {
        "schema_version": SCHEMA_VERSION,
        "accepted": accepted,
        "requires_repair": not accepted,
        "final_text": text,
        "used_memory_item_ids": declared_ids,
        "violations": violations,
        "template_origin": template_origin,
        "candidate_evaluation": candidate_evaluation.to_dict(),
        "runtime_validation": runtime_validation.to_dict(),
        "context_sha256": str(contract.get("context_sha256") or ""),
        "source_origin": "chatgpt_host_bridge",
    }


def host_model_context_hash_valid(contract: dict[str, Any]) -> bool:
    """Public fail-closed check used by the pending-request boundary."""

    return _context_hash_valid(contract if isinstance(contract, dict) else {})


def _sanitize_memory_items(value: Any) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for raw in value if isinstance(value, list) else []:
        if not isinstance(raw, dict):
            continue
        item: dict[str, Any] = {}
        for key in _MEMORY_ITEM_KEYS:
            if key in raw:
                item[key] = _sanitize_json_value(raw.get(key), depth=0)
        if str(item.get("item_id") or "").strip() and str(item.get("excerpt") or "").strip():
            items.append(item)
        if len(items) >= 8:
            break
    return items


def _sanitize_used_memory_ids(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    ids: list[str] = []
    for raw in value:
        item_id = re.sub(r"[^0-9A-Za-z_.:/-]+", "_", str(raw or "").strip()).strip("_")
        if item_id and item_id not in ids:
            ids.append(item_id)
        if len(ids) >= 8:
            break
    return ids


def _sanitize_json_value(value: Any, *, depth: int) -> Any:
    if depth >= 10:
        return "[TRUNCATED_DEPTH]"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return _bounded_text(value, 16_000 if depth == 0 else 8_000)
    if isinstance(value, list):
        return [_sanitize_json_value(item, depth=depth + 1) for item in value[:64]]
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for raw_key, raw_value in list(value.items())[:128]:
            key = str(raw_key or "").strip()
            if not key or _blocked_key(key):
                continue
            out[key] = _sanitize_json_value(raw_value, depth=depth + 1)
        return out
    return _bounded_text(value, 2_000)


def _blocked_key(key: str) -> bool:
    folded = key.lower().replace("-", "_")
    return any(marker in folded for marker in _BLOCKED_KEY_MARKERS)


def _bounded_text(value: Any, limit: int) -> str:
    text = str(value or "").replace("\x00", "").strip()
    return text[: max(0, int(limit))]


def _sha256(value: dict[str, Any]) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _context_hash_valid(contract: dict[str, Any]) -> bool:
    supplied = str(contract.get("context_sha256") or "")
    if not re.fullmatch(r"[0-9a-f]{64}", supplied):
        return False
    unsigned = {key: value for key, value in contract.items() if key != "context_sha256"}
    return _sha256(unsigned) == supplied
