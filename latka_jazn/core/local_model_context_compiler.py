from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping
import hashlib
import json
import math
import re

from latka_jazn.version import schema_version


SCHEMA_VERSION = schema_version("local_model_context_compiler")
DEFAULT_CONTEXT_MAX_CHARS = 16_000
MIN_CONTEXT_MAX_CHARS = 8_000
MAX_CONTEXT_MAX_CHARS = 32_768
MAX_REQUIRED_IDS_PER_KIND = 64
MAX_REQUIRED_ID_CHARS = 160

SECTION_BUDGETS: dict[str, int] = {
    "schema_version": 160,
    "user_message": 2_400,
    "detected_intent": 240,
    "route": 240,
    "nlg_plan": 2_400,
    "operational_thought_frame": 1_200,
    "voice_source_contract": 1_800,
    "allowed_memory_items": 4_800,
    "forbidden_claims": 1_400,
    "required_truth_boundaries": 2_200,
    "output_instructions": 2_400,
    "token_budget_hint": 120,
    "dialogue_context": 2_400,
    "self_state_runtime": 1_000,
    "turn_response_policy": 2_200,
    "full_canon_model_context": 5_600,
    "required_reference_ids": 2_400,
}

_SELECTED_SECTIONS = tuple(key for key in SECTION_BUDGETS if key != "required_reference_ids")
_DROP_ORDER = (
    "operational_thought_frame",
    "self_state_runtime",
    "forbidden_claims",
    "required_truth_boundaries",
    "voice_source_contract",
    "dialogue_context",
    "allowed_memory_items",
)
_PRIVATE_OR_RAW_KEYS = frozenset({
    "raw_payload",
    "raw_database",
    "database_dump",
    "private_chain_of_thought",
    "chain_of_thought",
    "hidden_reasoning",
    "sqlite_dump",
    "conversation_archive_raw",
})


@dataclass(slots=True, frozen=True)
class LocalModelContextCompilation:
    context: dict[str, Any]
    diagnostics: dict[str, Any]


def _json_text(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def _json_chars(value: Any) -> int:
    return len(_json_text(value))


def _safe_scalar(value: Any, *, max_chars: int) -> str | int | float | bool | None:
    if value is None or isinstance(value, (int, float, bool)):
        return value
    return str(value or "")[:max_chars]


def _dedupe_values(values: Iterable[Any]) -> list[Any]:
    result: list[Any] = []
    seen: set[str] = set()
    for value in values:
        fingerprint = hashlib.sha256(_json_text(value).encode("utf-8")).hexdigest()
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        result.append(value)
    return result


def _bounded_value(value: Any, *, depth: int = 0) -> Any:
    if depth >= 4:
        return _safe_scalar(value, max_chars=600)
    if isinstance(value, str):
        return value[:1_600]
    if value is None or isinstance(value, (int, float, bool)):
        return value
    if isinstance(value, (list, tuple)):
        return _dedupe_values(
            _bounded_value(item, depth=depth + 1)
            for item in list(value)[:24]
        )
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for raw_key, item in list(value.items())[:64]:
            key = str(raw_key)
            if key.casefold() in _PRIVATE_OR_RAW_KEYS:
                continue
            result[key] = _bounded_value(item, depth=depth + 1)
        return result
    return str(value)[:600]


def _fit_string(value: str, budget: int) -> str:
    if _json_chars(value) <= budget:
        return value
    low = 0
    high = len(value)
    while low < high:
        middle = (low + high + 1) // 2
        if _json_chars(value[:middle]) <= budget:
            low = middle
        else:
            high = middle - 1
    return value[:low]


def _fit_value(value: Any, *, budget: int) -> tuple[Any, bool]:
    bounded = _bounded_value(value)
    if _json_chars(bounded) <= budget:
        return bounded, False
    if isinstance(bounded, str):
        return _fit_string(bounded, budget), True
    if isinstance(bounded, list):
        fitted: list[Any] = []
        for item in bounded:
            item_budget = max(96, min(budget, budget - _json_chars(fitted) - 2))
            candidate, _ = _fit_value(item, budget=item_budget)
            if _json_chars([*fitted, candidate]) > budget:
                break
            fitted.append(candidate)
        return fitted, True
    if isinstance(bounded, dict):
        fitted_dict: dict[str, Any] = {}
        for key, item in bounded.items():
            remaining = max(96, budget - _json_chars(fitted_dict) - len(key) - 8)
            candidate, _ = _fit_value(item, budget=remaining)
            next_value = {**fitted_dict, key: candidate}
            if _json_chars(next_value) > budget:
                continue
            fitted_dict[key] = candidate
        return fitted_dict, True
    return bounded, True


def _query_terms(user_text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[0-9A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż_-]{3,}", user_text.casefold())
        if len(token) >= 3
    }


def _memory_relevance(item: Mapping[str, Any], terms: set[str], index: int) -> tuple[float, int]:
    searchable = " ".join(
        str(item.get(key) or "")
        for key in ("excerpt", "relevance_reason", "source", "item_id")
    ).casefold()
    overlap = sum(1 for term in terms if term in searchable)
    try:
        confidence = float(item.get("confidence") or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0
    return overlap * 4.0 + max(0.0, min(1.0, confidence)), -index


def _prepare_memory_items(value: Any, *, user_text: str) -> list[Any]:
    if not isinstance(value, (list, tuple)):
        return []
    terms = _query_terms(user_text)
    candidates = [item for item in value if isinstance(item, Mapping)]
    ranked = sorted(
        enumerate(candidates),
        key=lambda pair: _memory_relevance(pair[1], terms, pair[0]),
        reverse=True,
    )
    deduped: list[Any] = []
    seen_ids: set[str] = set()
    seen_content: set[str] = set()
    for _, item in ranked:
        item_id = str(item.get("item_id") or item.get("id") or "").strip()
        content_key = hashlib.sha256(
            " ".join(str(item.get(key) or "") for key in ("excerpt", "source")).encode("utf-8")
        ).hexdigest()
        if (item_id and item_id in seen_ids) or content_key in seen_content:
            continue
        if item_id:
            seen_ids.add(item_id)
        seen_content.add(content_key)
        deduped.append(dict(item))
    return deduped[:12]


def _safe_identifier(value: Any) -> str:
    text = str(value or "").strip()
    text = re.sub(r"[^0-9A-Za-z_.:/-]+", "_", text).strip("_")
    return text[:MAX_REQUIRED_ID_CHARS]


def _identifier_list(values: Any) -> tuple[list[str], bool]:
    if isinstance(values, str):
        source = [values]
    elif isinstance(values, (list, tuple, set)):
        source = list(values)
    else:
        source = []
    normalized = list(dict.fromkeys(filter(None, (_safe_identifier(item) for item in source))))
    return normalized[:MAX_REQUIRED_IDS_PER_KIND], len(normalized) > MAX_REQUIRED_IDS_PER_KIND


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return list(value)
    return [value]


def _required_reference_ids(
    raw: Mapping[str, Any],
    *,
    selected_memory_items: list[Any],
) -> tuple[dict[str, list[str]], bool]:
    explicit_raw = raw.get("required_reference_ids")
    explicit = dict(explicit_raw) if isinstance(explicit_raw, Mapping) else {}
    dialogue_raw = raw.get("dialogue_context")
    dialogue = dict(dialogue_raw) if isinstance(dialogue_raw, Mapping) else {}
    task_raw = dialogue.get("dialogue_task_state") or dialogue.get("previous_task_state")
    task = dict(task_raw) if isinstance(task_raw, Mapping) else {}
    policy_raw = raw.get("turn_response_policy")
    policy = dict(policy_raw) if isinstance(policy_raw, Mapping) else {}
    goals, goal_overflow = _identifier_list([
        *_as_list(explicit.get("goal") or explicit.get("goals")),
        task.get("task_id"),
        task.get("task_key"),
        task.get("goal_id"),
        task.get("active_goal"),
    ])
    constraints, constraint_overflow = _identifier_list([
        *_as_list(explicit.get("constraint") or explicit.get("constraints")),
        *_as_list(policy.get("required_components")),
    ])
    evidence, evidence_overflow = _identifier_list([
        *_as_list(explicit.get("evidence") or explicit.get("evidence_ids")),
        *(
            item.get("item_id") or item.get("id")
            for item in selected_memory_items
            if isinstance(item, Mapping)
        ),
    ])
    return {
        "goal": goals,
        "constraint": constraints,
        "evidence": evidence,
    }, bool(goal_overflow or constraint_overflow or evidence_overflow)


def _prepare_full_canon(value: Any) -> dict[str, Any]:
    full = dict(value) if isinstance(value, Mapping) else {}
    immutable_raw = full.get("immutable_canon")
    immutable = dict(immutable_raw) if isinstance(immutable_raw, Mapping) else {}
    return {
        "schema_version": full.get("schema_version"),
        "read_only": full.get("read_only"),
        "immutable_canon_sha256": full.get("immutable_canon_sha256"),
        "voice_source_contract": full.get("voice_source_contract"),
        "canon_presence": full.get("canon_presence"),
        "immutable_canon": {
            key: immutable.get(key)
            for key in (
                "identity_core",
                "character_profile",
                "relation_canon",
                "memory_truth_boundary",
                "symbolic_world",
            )
            if immutable.get(key) not in (None, "", [], {})
        },
    }


def compile_local_model_context(
    value: Any,
    *,
    user_text: str = "",
    max_chars: int = DEFAULT_CONTEXT_MAX_CHARS,
) -> LocalModelContextCompilation:
    raw = dict(value) if isinstance(value, Mapping) else {}
    effective_max = min(
        MAX_CONTEXT_MAX_CHARS,
        max(MIN_CONTEXT_MAX_CHARS, int(max_chars)),
    )
    original_chars = _json_chars(raw)
    prepared_memory_items = _prepare_memory_items(
        raw.get("allowed_memory_items"),
        user_text=user_text or str(raw.get("user_message") or ""),
    )
    references, reference_overflow = _required_reference_ids(
        raw,
        selected_memory_items=prepared_memory_items,
    )
    compact: dict[str, Any] = {}
    section_diagnostics: dict[str, dict[str, Any]] = {}
    deduplicated_current_user_message = False

    for key in _SELECTED_SECTIONS:
        section = raw.get(key)
        if section in (None, "", [], {}):
            continue
        if key == "user_message" and user_text and str(section).strip() == user_text.strip():
            deduplicated_current_user_message = True
            continue
        if key == "allowed_memory_items":
            section = prepared_memory_items
        elif key == "full_canon_model_context":
            section = _prepare_full_canon(section)
        budget = SECTION_BUDGETS[key]
        fitted, truncated = _fit_value(section, budget=budget)
        if fitted not in (None, "", [], {}):
            compact[key] = fitted
        section_diagnostics[key] = {
            "budget_chars": budget,
            "input_chars": _json_chars(section),
            "output_chars": _json_chars(fitted),
            "truncated": truncated,
        }

    fitted_references, references_truncated = _fit_value(
        references,
        budget=SECTION_BUDGETS["required_reference_ids"],
    )
    if fitted_references not in (None, "", [], {}):
        compact["required_reference_ids"] = fitted_references
    section_diagnostics["required_reference_ids"] = {
        "budget_chars": SECTION_BUDGETS["required_reference_ids"],
        "input_chars": _json_chars(references),
        "output_chars": _json_chars(fitted_references),
        "truncated": references_truncated,
    }

    removed_sections: list[str] = []
    for key in _DROP_ORDER:
        if _json_chars(compact) <= effective_max:
            break
        if key in compact:
            compact.pop(key, None)
            removed_sections.append(key)

    compile_status = "ready"
    error_code: str | None = None
    required_ids_preserved = fitted_references == references and not reference_overflow
    if not required_ids_preserved:
        compile_status = "blocked_required_reference_overflow"
        error_code = "local_context_required_reference_overflow"
    elif _json_chars(compact) > effective_max:
        minimal = {
            key: compact.get(key)
            for key in (
                "detected_intent",
                "route",
                "nlg_plan",
                "turn_response_policy",
                "output_instructions",
                "required_reference_ids",
            )
            if compact.get(key) not in (None, "", [], {})
        }
        canon = compact.get("full_canon_model_context")
        canon_value = dict(canon) if isinstance(canon, Mapping) else {}
        minimal["full_canon_model_context"] = {
            "immutable_canon_sha256": canon_value.get("immutable_canon_sha256"),
            "canon_presence": canon_value.get("canon_presence"),
        }
        compact = minimal
        if _json_chars(compact) > effective_max:
            compile_status = "blocked_total_context_budget"
            error_code = "local_context_total_budget_exceeded"

    if error_code is not None:
        compact = {
            "schema_version": SCHEMA_VERSION,
            "context_compile_status": compile_status,
            "required_reference_ids": fitted_references,
            "context_budget_notice": "local model generation blocked; deterministic runtime fallback required",
        }

    final_chars = _json_chars(compact)
    estimated_tokens = int(math.ceil(final_chars / 4.0))
    diagnostics = {
        "schema_version": SCHEMA_VERSION,
        "ok": error_code is None,
        "status": compile_status,
        "error_code": error_code,
        "original_context_chars": original_chars,
        "compacted_context_chars": final_chars,
        "estimated_context_tokens": estimated_tokens,
        "context_max_chars": effective_max,
        "context_compacted": original_chars > final_chars,
        "section_budgets": dict(SECTION_BUDGETS),
        "sections": section_diagnostics,
        "removed_sections": removed_sections,
        "required_reference_counts": {
            key: len(values) for key, values in references.items()
        },
        "required_reference_ids_preserved": required_ids_preserved,
        "deduplicated_current_user_message": deduplicated_current_user_message,
        "raw_payload_included": False,
        "private_reasoning_included": False,
        "diagnostics_content_free": True,
        "fallback_required": error_code is not None,
    }
    return LocalModelContextCompilation(context=compact, diagnostics=diagnostics)


__all__ = [
    "DEFAULT_CONTEXT_MAX_CHARS",
    "LocalModelContextCompilation",
    "MAX_CONTEXT_MAX_CHARS",
    "SCHEMA_VERSION",
    "SECTION_BUDGETS",
    "compile_local_model_context",
]
