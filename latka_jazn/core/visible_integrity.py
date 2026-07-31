from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import hashlib

from latka_jazn.core.json_types import (
    is_string_keyed_mapping,
    mapping_object,
)
from latka_jazn.core.message_envelope import (
    TIMESTAMP_HEADER_RE,
    extract_body_from_visible_text,
    normalize_newlines,
    parse_timestamp_header,
)
from latka_jazn.core.timestamp_policy import (
    TIMESTAMP_ALLOW_DEGRADED_LOCAL_VISIBLE,
    TIMESTAMP_MAX_AGE_SECONDS,
    TIMESTAMP_REQUIRE_TRUSTED_IN_FINAL_VISIBLE,
    timestamp_runtime_policy,
)
from latka_jazn.version import schema_version

RUNTIME_OWNED_NON_FALLBACK_CLASSIFICATIONS = frozenset({"rule_handler_response"})
RENDER_ARTIFACTS = (
    "aaaktywny", "aaktywny", "prrzez", "nieddziela", "niedzielaa",
    "pierwszoossobową", "pierwszoosobowąą", "GMMT", "2026-066", "221:",
    "13:43:228", "rozmawiać ć", "Uwa ażam", "operacyjnnego", "ddebug", "techniiczna",
)


def _sha(text: str) -> str:
    return hashlib.sha256(normalize_newlines(text).encode("utf-8")).hexdigest()


def _canonical_body(text: str) -> str:
    return normalize_newlines(text)


def _visible_body(timestamp_header: str, text: str) -> str | None:
    value = normalize_newlines(text)
    if not timestamp_header or not value.startswith(timestamp_header + "\n"):
        return None
    remainder = value[len(timestamp_header) + 1:]
    if "\n\n" not in remainder:
        return None
    _author_line, body = remainder.split("\n\n", 1)
    return body


def evaluate_origin_truth(
    decision: Mapping[str, Any] | None,
    *,
    body: str,
    final_visible_text: str,
    timestamp_header: str = "",
) -> tuple[bool, list[str]]:
    decision = dict(decision or {})
    classification = str(decision.get("fallback_classification") or "not_fallback")
    validation = mapping_object(decision.get("final_answer_validation"))
    accepted = validation.get("accepted") is True and validation.get("must_regenerate") is not True
    template = mapping_object(decision.get("template_origin"))
    provenance = mapping_object(decision.get("runtime_provenance"))
    canonical_body = _canonical_body(body)
    visible_body = _visible_body(timestamp_header, final_visible_text)
    reasons: list[str] = []

    if not accepted:
        reasons.append("validator_not_accepted")
    if not canonical_body or visible_body != canonical_body:
        reasons.append("visible_body_mismatch")
    if provenance:
        if _canonical_body(str(provenance.get("exact_runtime_text") or "")) != canonical_body:
            reasons.append("provenance_runtime_text_mismatch")
    else:
        reasons.append("runtime_provenance_missing")

    if classification == "rule_handler_response":
        handler = mapping_object(decision.get("handler_result"))
        handler_body = _canonical_body(str(handler.get("body") or ""))
        required = set(handler.get("required_components") or [])
        satisfied = set(handler.get("satisfied_components") or decision.get("handler_satisfied_components") or [])
        missing = set(handler.get("missing_components") or decision.get("handler_missing_components") or [])
        handler_name = str(handler.get("handler_name") or decision.get("handler_name") or "")
        provenance_handler = str(provenance.get("handler_name") or "")
        source_origin = str(provenance.get("source_origin_detail") or decision.get("source_origin_detail") or "")
        if not handler_body or handler_body != canonical_body:
            reasons.append("handler_body_mismatch")
        if missing or not required.issubset(satisfied):
            reasons.append("handler_required_components_missing")
        if template.get("template_id") or handler.get("template_origin"):
            reasons.append("template_fallback_not_runtime_owned")
        if not handler_name or provenance_handler != handler_name or not source_origin:
            reasons.append("rule_handler_provenance_missing")
        return not reasons, reasons

    if classification != "not_fallback":
        reasons.append("classified_fallback")
        return False, reasons

    if decision.get("model_generated") is True:
        if str(provenance.get("response_generation_mode") or "") != "runtime_model_guided":
            reasons.append("model_candidate_not_runtime_accepted")
        return not reasons, reasons

    finalization = mapping_object(decision.get("host_visible_finalization"))
    if finalization.get("accepted") is True:
        if str(finalization.get("final_visible_text") or "") != str(final_visible_text or ""):
            reasons.append("host_finalization_text_mismatch")
        if str(finalization.get("final_text_sha256") or "") != _sha(str(final_visible_text or "")):
            reasons.append("host_finalization_hash_mismatch")
        return not reasons, reasons

    reasons.append("not_fallback_without_provenance")
    return False, reasons


def _parse_sample(contract: Mapping[str, Any]) -> tuple[datetime | None, str | None]:
    raw = contract.get("sample_iso")
    if not raw:
        return None, "timestamp_sample_missing"
    try:
        sample = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None, "timestamp_sample_invalid"
    if sample.tzinfo is None:
        return None, "timestamp_sample_naive"
    return sample, None


def validate_visible_text(
    timestamp_header: str,
    text: str,
    *,
    timestamp_contract: Mapping[str, Any] | None = None,
    validation_passed: bool,
    origin_truth_valid: bool,
    expected_visible_hash: str | None = None,
    author_label: str | None = None,
    state_emoticon: str | None = None,
    expected_body: str | None = None,
) -> dict[str, Any]:
    visible = normalize_newlines(text)
    contract = dict(timestamp_contract or {})
    trusted = contract.get("trusted")
    source = str(contract.get("source") or "").strip()
    timezone_key = str(contract.get("timezone") or contract.get("timezone_key") or "").strip()
    sample, sample_error = _parse_sample(contract)
    header_dt = parse_timestamp_header(timestamp_header)
    has_timestamp = bool(timestamp_header) and visible.startswith(timestamp_header + "\n")
    header_shape_valid = bool(TIMESTAMP_HEADER_RE.fullmatch(str(timestamp_header or "").strip()))
    max_age_seconds = int(contract.get("max_age_seconds") or TIMESTAMP_MAX_AGE_SECONDS)
    freshness_seconds: int | None = None
    freshness_ok = False
    timestamp_matches_sample = False
    timezone_valid = False
    if sample is not None:
        freshness_seconds = abs(int((datetime.now(timezone.utc) - sample.astimezone(timezone.utc)).total_seconds()))
        freshness_ok = freshness_seconds <= max_age_seconds
        if header_dt is not None and timezone_key:
            try:
                zone = ZoneInfo(timezone_key)
                expected_local = sample.astimezone(zone).replace(tzinfo=None, microsecond=0)
                timestamp_matches_sample = header_dt == expected_local
                timezone_valid = True
            except ZoneInfoNotFoundError:
                timezone_valid = False
    trust_required = bool(contract.get("require_trusted_in_final_visible", TIMESTAMP_REQUIRE_TRUSTED_IN_FINAL_VISIBLE))
    degraded_allowed = bool(contract.get("allow_degraded_local_visible", TIMESTAMP_ALLOW_DEGRADED_LOCAL_VISIBLE))
    trust_declared = isinstance(trusted, bool)
    trust_ok = bool(trusted) or (trust_declared and degraded_allowed) or not trust_required
    source_ok = bool(source)

    envelope_shape_ok = True
    body_exact = True
    expected_author_line: str | None = None
    if author_label is not None or state_emoticon is not None or expected_body is not None:
        expected_author_line = f"{state_emoticon or ''} {author_label or ''}".strip()
        expected_prefix = f"{timestamp_header}\n{expected_author_line}\n\n"
        envelope_shape_ok = bool(author_label and state_emoticon and visible.startswith(expected_prefix))
        if expected_body is not None:
            extracted = extract_body_from_visible_text(
                visible,
                timestamp_header=timestamp_header,
                state_emoticon=str(state_emoticon or ""),
                author_label=str(author_label or ""),
            )
            body_exact = extracted == normalize_newlines(expected_body)

    text_hash = _sha(visible)
    hash_valid = expected_visible_hash in (None, "", text_hash)
    errors: list[str] = []
    if not has_timestamp: errors.append("timestamp_missing")
    if not header_shape_valid: errors.append("timestamp_header_invalid")
    if sample_error: errors.append(sample_error)
    if not source_ok: errors.append("timestamp_source_missing")
    if not timezone_key: errors.append("timestamp_timezone_missing")
    elif not timezone_valid: errors.append("timestamp_timezone_invalid")
    if not timestamp_matches_sample: errors.append("timestamp_header_sample_mismatch")
    if not freshness_ok: errors.append("timestamp_stale")
    if not trust_declared: errors.append("timestamp_trust_missing")
    if not trust_ok: errors.append("timestamp_trust_invalid")
    if not envelope_shape_ok: errors.append("message_envelope_invalid")
    if not body_exact: errors.append("visible_body_mismatch")
    if not validation_passed: errors.append("answer_validation_failed")
    if not origin_truth_valid: errors.append("origin_truth_invalid")
    if not hash_valid: errors.append("visible_text_hash_mismatch")
    timestamp_valid = bool(
        has_timestamp and header_shape_valid and sample is not None and source_ok and timezone_valid
        and timestamp_matches_sample and freshness_ok and trust_declared and trust_ok
    )
    valid = bool(timestamp_valid and envelope_shape_ok and body_exact and validation_passed and origin_truth_valid and hash_valid)
    return {
        "schema_version": schema_version("final_visible_integrity"),
        "timestamp_policy": timestamp_runtime_policy(),
        "timestamp_header": timestamp_header,
        "timestamp_present": has_timestamp,
        "timestamp_header_shape_valid": header_shape_valid,
        "timestamp_header_matches_sample": timestamp_matches_sample,
        "timestamp_source": source or None,
        "timestamp_trusted": trusted,
        "timestamp_sample_iso": contract.get("sample_iso"),
        "timestamp_timezone": timezone_key or None,
        "timestamp_timezone_valid": timezone_valid,
        "timestamp_freshness_seconds": freshness_seconds,
        "timestamp_max_age_seconds": max_age_seconds,
        "timestamp_freshness_ok": freshness_ok,
        "timestamp_trust_ok": trust_ok,
        "timestamp_degraded_allowed": degraded_allowed,
        "timestamp_degraded_visible_ok": bool(degraded_allowed and trusted is False and timestamp_valid),
        "timestamp_valid": timestamp_valid,
        "author_line": expected_author_line,
        "message_envelope_valid": envelope_shape_ok,
        "body_exact": body_exact,
        "validation_passed": bool(validation_passed),
        "origin_truth_valid": bool(origin_truth_valid),
        "hash_valid": hash_valid,
        "valid": valid,
        "errors": errors,
        "text_sha256": text_hash,
    }


def validate_result_integrity(result: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(result or {})
    contract = mapping_object(result.get("final_response_contract"))
    decision = mapping_object(result.get("conversation_decision"))
    trace = mapping_object(result.get("trace"))
    final_text = str(result.get("final_visible_text") if "final_visible_text" in result else contract.get("final_visible_text") or "")
    timestamp_header = str(trace.get("timestamp_header") or contract.get("timestamp_header") or "")
    body = str(contract.get("body") if "body" in contract else result.get("exact_runtime_text") or "")
    origin_valid, origin_errors = evaluate_origin_truth(decision, body=body, final_visible_text=final_text, timestamp_header=timestamp_header)
    validation_value = decision.get("final_answer_validation")
    validation = (
        validation_value
        if is_string_keyed_mapping(validation_value)
        else mapping_object(contract.get("validation"))
    )
    validation_passed = bool(validation.get("accepted") is True and validation.get("must_regenerate") is not True)
    provenance_value = result.get("runtime_provenance")
    provenance = (
        provenance_value
        if is_string_keyed_mapping(provenance_value)
        else mapping_object(decision.get("runtime_provenance"))
    )
    decision_provenance = mapping_object(decision.get("runtime_provenance"))
    expected_hash = str(provenance.get("visible_answer_hash") or contract.get("visible_answer_hash") or "") or None
    timestamp_payload = dict(mapping_object(decision.get("timestamp_contract")))
    timestamp_payload.setdefault("trusted", contract.get("timestamp_trusted"))
    timestamp_payload.setdefault("source", contract.get("timestamp_source"))
    timestamp_payload.setdefault("sample_iso", contract.get("timestamp_sample_iso"))
    timestamp_payload.setdefault("timezone", contract.get("timezone"))
    integrity = validate_visible_text(
        timestamp_header,
        final_text,
        timestamp_contract=timestamp_payload,
        validation_passed=validation_passed,
        origin_truth_valid=origin_valid,
        expected_visible_hash=expected_hash,
        author_label=str(contract.get("author_label") or "") or None,
        state_emoticon=str(contract.get("state_emoticon") or "") or None,
        expected_body=body,
    )
    errors = list(integrity.get("errors") or []) + origin_errors
    if decision_provenance and any(
        str(decision_provenance.get(field) or "") != str(provenance.get(field) or "")
        for field in ("exact_runtime_text", "runtime_text_hash", "visible_answer_text", "visible_answer_hash")
    ):
        errors.append("runtime_provenance_layer_mismatch")
    visible_provenance_text = str(provenance.get("visible_answer_text") or "")
    if not visible_provenance_text:
        errors.append("visible_answer_text_missing")
    elif visible_provenance_text != final_text:
        errors.append("visible_answer_text_mismatch")
    provenance_visible_hash = str(provenance.get("visible_answer_hash") or "")
    if not provenance_visible_hash:
        errors.append("visible_answer_hash_missing")
    elif provenance_visible_hash != _sha(visible_provenance_text):
        errors.append("provenance_visible_answer_hash_mismatch")
    contract_text = str(contract.get("final_visible_text") or "")
    if contract_text != final_text:
        errors.append("final_response_contract_text_mismatch")
    contract_visible_hash = str(contract.get("visible_answer_hash") or "")
    if contract_visible_hash and contract_visible_hash != provenance_visible_hash:
        errors.append("final_response_contract_visible_hash_mismatch")

    provenance_runtime_text = str(provenance.get("exact_runtime_text") or "")
    result_runtime_text = str(result.get("exact_runtime_text") or "")
    contract_runtime_text = str(contract.get("runtime_exact_text") or contract.get("body") or "")
    exact_runtime_text = provenance_runtime_text
    if not provenance_runtime_text: errors.append("exact_runtime_text_missing")
    if result_runtime_text != provenance_runtime_text: errors.append("result_exact_runtime_text_mismatch")
    if contract_runtime_text != provenance_runtime_text: errors.append("final_response_contract_runtime_text_mismatch")
    expected_runtime_hash = str(provenance.get("runtime_text_hash") or "")
    if not expected_runtime_hash: errors.append("runtime_text_hash_missing")
    elif expected_runtime_hash != _sha(exact_runtime_text): errors.append("runtime_text_hash_mismatch")
    contract_runtime_hash = str(contract.get("runtime_text_hash") or "")
    if contract_runtime_hash and contract_runtime_hash != expected_runtime_hash:
        errors.append("final_response_contract_runtime_hash_mismatch")
    for field in ("author_id", "author_label", "author_source"):
        if not str(contract.get(field) or "").strip():
            errors.append(f"{field}_missing")
    if str(contract.get("author_label") or "") == "Łatka" and str(contract.get("author_source") or "") != "jazn_runtime":
        errors.append("author_source_mismatch")
    for artifact in RENDER_ARTIFACTS:
        if artifact in final_text or artifact in exact_runtime_text:
            errors.append(f"render_artifact_detected:{artifact}")
    if "\ufffd" in final_text or "\ufffd" in exact_runtime_text:
        errors.append("unicode_replacement_character_detected")
    integrity["errors"] = sorted(set(errors))
    integrity["checked_artifact_count"] = len(RENDER_ARTIFACTS)
    integrity["valid"] = bool(integrity.get("valid") and not errors)
    return integrity


def enforce_integrity_consensus(result: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    updated = dict(result or {})
    contract = dict(mapping_object(updated.get("final_response_contract")))
    contract_integrity = dict(mapping_object(contract.get("final_visible_integrity")))
    result_integrity = dict(mapping_object(updated.get("final_visible_integrity")))
    gate = dict(mapping_object(updated.get("runtime_truth_gate")))
    session = dict(mapping_object(updated.get("session_provenance")))
    values = {
        "pre_repair_contract": updated.get("final_visible_integrity_pre_repair_contract_valid"),
        "result": result_integrity.get("valid"),
        "contract": contract_integrity.get("valid"),
        "runtime_truth_gate": gate.get("final_visible_integrity_valid"),
        "session_provenance": session.get("final_visible_integrity_valid"),
    }
    declared = [value for value in values.values() if isinstance(value, bool)]
    mismatch = bool(declared and any(value != declared[0] for value in declared[1:]))
    canonical = bool(contract_integrity.get("valid") and result_integrity.get("valid"))
    final_valid = bool(canonical and not mismatch)
    result_integrity["valid"] = final_valid
    result_integrity["consensus"] = not mismatch
    result_integrity["consensus_values"] = values
    contract_integrity["valid"] = final_valid
    contract_integrity["consensus"] = not mismatch
    gate["final_visible_integrity_valid"] = final_valid
    session["final_visible_integrity_valid"] = final_valid
    contract["final_visible_integrity"] = contract_integrity
    updated["final_visible_integrity"] = result_integrity
    updated["final_response_contract"] = contract
    updated["runtime_truth_gate"] = gate
    updated["session_provenance"] = session
    if mismatch:
        updated["ok"] = False
        updated["normal_response_blocked"] = True
        updated["error_code"] = "integrity_consensus_mismatch"
        updated["runtime_response_status"] = "blocked_by_integrity_consensus"
        gate["ok"] = False
        gate["normal_response_allowed"] = False
        gate["error_code"] = "integrity_consensus_mismatch"
        gate.setdefault("errors", []).append("integrity_consensus_mismatch")
    return updated, {
        "schema_version": schema_version("final_visible_integrity_consensus"),
        "valid": final_valid,
        "mismatch": mismatch,
        "values": values,
        "error_code": "integrity_consensus_mismatch" if mismatch else None,
    }
