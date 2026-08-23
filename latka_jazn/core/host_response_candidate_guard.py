from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from latka_jazn.core.message_envelope import strip_recognized_visible_envelope
from latka_jazn.core.model_context_compiler import compile_model_context
from latka_jazn.core.nlg_planner import build_nlg_plan
from latka_jazn.core.operational_thought_frame import build_operational_thought_frame
from latka_jazn.core.response_candidate import ResponseCandidate
from latka_jazn.core.response_candidate_evaluator import evaluate_response_candidate
from latka_jazn.core.runtime_answer_validator import RuntimeAnswerValidator
from latka_jazn.core.template_registry import TemplateRegistry
from latka_jazn.version import schema_version


SCHEMA_VERSION = schema_version("host_response_candidate_guard")
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


def build_host_generation_context(
    model_context: dict[str, Any],
    *,
    detected_intent: str,
    route: str,
    context_origin: str = "runtime_model_synthesis",
) -> dict[str, Any]:
    """Return the bounded context the host may use to word one reply.

    This is a projection of the current v16 model context, not a second model
    bridge or a source of identity. Raw runtime rows and credential-shaped keys
    are deliberately excluded before the context hash is calculated.
    """

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
        "context_origin": _bounded_text(context_origin, 80),
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


def build_host_generation_context_from_runtime(
    result: dict[str, Any],
    *,
    user_text: str,
    detected_intent: str,
    route: str,
) -> dict[str, Any]:
    """Compile the same canonical model context when phase 1 did not retain it."""

    frame_value = result.get("cognitive_frame")
    frame = frame_value if isinstance(frame_value, dict) else {}
    decision_value = result.get("conversation_decision")
    decision = decision_value if isinstance(decision_value, dict) else {}
    policy_value = frame.get("turn_response_policy") or decision.get("turn_response_policy")
    response_policy = policy_value if isinstance(policy_value, dict) else {}
    nlg_plan = build_nlg_plan(
        user_text=user_text,
        cognitive_frame=frame,
        response_policy=response_policy,
        route=route,
        detected_intent=detected_intent,
    )
    thought_frame = build_operational_thought_frame(
        user_text=user_text,
        nlg_plan=nlg_plan,
        cognitive_frame=frame,
        response_policy=response_policy,
    )
    packet = compile_model_context(
        user_text=user_text,
        cognitive_frame=frame,
        nlg_plan=nlg_plan,
        thought_frame=thought_frame,
        response_policy=response_policy,
    )
    return build_host_generation_context(
        packet.to_dict(),
        detected_intent=detected_intent,
        route=route,
        context_origin="phase1_reconstructed_compatibility",
    )


def validate_host_generation_context(value: dict[str, Any]) -> bool:
    contract = value if isinstance(value, dict) else {}
    supplied = str(contract.get("context_sha256") or "")
    if not re.fullmatch(r"[0-9a-f]{64}", supplied):
        return False
    unsigned = {key: item for key, item in contract.items() if key != "context_sha256"}
    return _sha256(unsigned) == supplied


def evaluate_host_response_candidate(
    *,
    final_text: str,
    host_generation_context: dict[str, Any],
    used_memory_item_ids: list[str] | None,
) -> dict[str, Any]:
    """Treat host wording as an untrusted candidate before persistence."""

    contract = host_generation_context if isinstance(host_generation_context, dict) else {}
    model_context_value = contract.get("model_context")
    model_context = model_context_value if isinstance(model_context_value, dict) else {}
    current_turn_value = contract.get("current_turn")
    current_turn = current_turn_value if isinstance(current_turn_value, dict) else {}
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
    if not validate_host_generation_context(contract):
        violations.append("host_generation_context_sha256_mismatch")
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
        generation_reason="generated_from_host_generation_context",
        source_origin="chatgpt_host_finalizer",
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
    compatibility_context = str(contract.get("context_origin") or "") == "phase1_reconstructed_compatibility"
    if not runtime_validation.accepted and not compatibility_context:
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
        "runtime_validation_enforced": not compatibility_context,
        "context_origin": contract.get("context_origin"),
        "context_sha256": str(contract.get("context_sha256") or ""),
        "source_origin": "chatgpt_host_finalizer",
    }


def _sanitize_memory_items(value: Any) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for raw in value if isinstance(value, list) else []:
        if not isinstance(raw, dict):
            continue
        item = {
            key: _sanitize_json_value(raw.get(key), depth=0)
            for key in _MEMORY_ITEM_KEYS
            if key in raw
        }
        if str(item.get("item_id") or "").strip() and str(item.get("excerpt") or "").strip():
            items.append(item)
        if len(items) >= 8:
            break
    return items


def _sanitize_used_memory_ids(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    identifiers: list[str] = []
    for raw in value:
        item_id = re.sub(r"[^0-9A-Za-z_.:/-]+", "_", str(raw or "").strip()).strip("_")
        if item_id and item_id not in identifiers:
            identifiers.append(item_id)
        if len(identifiers) >= 8:
            break
    return identifiers


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
    return str(value or "").replace("\x00", "").strip()[: max(0, int(limit))]


def _sha256(value: dict[str, Any]) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
