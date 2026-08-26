from __future__ import annotations

import hmac
from pathlib import Path
from typing import Any, Mapping, Protocol, cast

from latka_jazn.bridge.secure_host_runtime_gateway import GatewayError
from latka_jazn.core.chatgpt_host_pending_store import HostRequestStoreError
from latka_jazn.core.chatgpt_host_recovery import (
    recover_pending_host_request,
    reissue_pending_continuation,
)


class HostRuntimeRecoveryGateway(Protocol):
    def result(self, request_id: str) -> dict[str, Any]: ...


def _object_or_none(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return cast(dict[str, Any], value)
    return None


def _runtime_result_from(response: dict[str, Any]) -> dict[str, Any]:
    nested = _object_or_none(response.get("result"))
    return nested if nested is not None else response


def _presentation_from(response: dict[str, Any]) -> dict[str, Any]:
    nested = _object_or_none(response.get("chatgpt_host_presentation"))
    if nested is not None:
        return nested
    if str(response.get("type") or "") == "chatgpt_host_presentation" or response.get("action"):
        return response
    return {}


def _tool_error(reason: str, *, response: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "content": [{"type": "text", "text": f"Jaźń host recovery failed safely: {reason}."}],
        "structuredContent": {
            "ok": False,
            "action": "host_diagnostic",
            "reason": reason,
            "recovery_attempted": True,
            "must_not_resubmit_user_message": True,
        },
        "_meta": {"runtime_response": response or {}},
        "isError": True,
    }


def _display_exact(
    runtime_result: dict[str, Any],
    presentation: dict[str, Any],
) -> dict[str, Any]:
    final_text = str(
        presentation.get("final_visible_text")
        or runtime_result.get("final_visible_text")
        or ""
    )
    checks = _object_or_none(presentation.get("runtime_checks")) or {}
    integrity = _object_or_none(runtime_result.get("final_visible_integrity"))
    if integrity is None:
        final_contract = _object_or_none(runtime_result.get("final_response_contract")) or {}
        integrity = _object_or_none(final_contract.get("final_visible_integrity")) or {}
    integrity_valid = (
        integrity.get("valid") is True
        or checks.get("final_visible_integrity_valid") is True
    )
    truth_ok = checks.get("runtime_truth_gate_ok")
    if truth_ok is None:
        truth_gate = runtime_result.get("runtime_truth_gate")
        truth_ok = truth_gate.get("ok") if isinstance(truth_gate, dict) else None
    if not final_text or integrity_valid is not True or truth_ok is not True:
        return _tool_error(
            "validated_final_visible_text_missing_after_recovery",
            response=runtime_result,
        )
    return {
        "content": [{"type": "text", "text": final_text}],
        "structuredContent": {
            "ok": True,
            "action": "display_exact",
            "final_visible_text": final_text,
            "final_text_sha256": presentation.get("final_text_sha256"),
            "turn_id": presentation.get("turn_id"),
            "trace_id": presentation.get("trace_id"),
            "must_display_exactly": True,
            "recovered_existing_request": True,
            "must_not_resubmit_user_message": True,
        },
        "_meta": {
            "transport": "secure_loopback_gateway",
            "phase": presentation.get("phase"),
            "recovery": "existing_daemon_request",
        },
        "isError": False,
    }


def _validate_runtime_binding(
    *,
    daemon_request_id: str,
    record: Mapping[str, Any],
    presentation: Mapping[str, Any],
    runtime_result: Mapping[str, Any],
) -> None:
    binding_value = record.get("binding")
    binding = dict(binding_value) if isinstance(binding_value, Mapping) else {}
    bridge_value = presentation.get("chatgpt_host_bridge")
    if not isinstance(bridge_value, Mapping):
        bridge_value = runtime_result.get("chatgpt_host_bridge")
    bridge = dict(bridge_value) if isinstance(bridge_value, Mapping) else {}

    expected_turn_id = str(binding.get("turn_id") or "").strip()
    expected_trace_id = str(binding.get("trace_id") or "").strip()
    expected_hash = str(record.get("request_contract_hash") or "").strip().lower()

    runtime_request_id = str(
        bridge.get("daemon_request_id")
        or presentation.get("daemon_request_id")
        or ""
    ).strip()
    runtime_turn_id = str(
        bridge.get("turn_id")
        or presentation.get("turn_id")
        or ""
    ).strip()
    runtime_trace_id = str(
        bridge.get("trace_id")
        or presentation.get("trace_id")
        or ""
    ).strip()
    runtime_hash = str(bridge.get("host_request_contract_hash") or "").strip().lower()

    if runtime_request_id and not hmac.compare_digest(runtime_request_id, daemon_request_id):
        raise HostRequestStoreError("pending_host_recovery_request_mismatch")
    if runtime_turn_id and not hmac.compare_digest(runtime_turn_id, expected_turn_id):
        raise HostRequestStoreError("pending_host_recovery_turn_mismatch")
    if runtime_trace_id and expected_trace_id and not hmac.compare_digest(runtime_trace_id, expected_trace_id):
        raise HostRequestStoreError("pending_host_recovery_trace_mismatch")
    if runtime_hash and not hmac.compare_digest(runtime_hash, expected_hash):
        raise HostRequestStoreError("host_request_contract_hash_mismatch")


def run(
    *,
    root: Path,
    gateway: HostRuntimeRecoveryGateway,
    daemon_request_id: str,
    turn_id: str | None = None,
    host_request_contract_hash: str | None = None,
) -> dict[str, Any]:
    request_id = str(daemon_request_id or "").strip()
    if not request_id:
        return _tool_error("daemon_request_id_missing")

    try:
        envelope = gateway.result(request_id)
    except GatewayError as exc:
        return _tool_error(f"runtime_poll_failed:{exc}")

    runtime_result = _runtime_result_from(envelope)
    presentation = _presentation_from(runtime_result)
    action = str(presentation.get("action") or "").strip()

    if action == "display_exact":
        return _display_exact(runtime_result, presentation)

    status = str(envelope.get("status") or "").strip()
    if action == "poll_runtime" or (
        not action
        and status in {"queued", "running"}
        and _object_or_none(envelope.get("result")) is None
    ):
        return {
            "content": [{
                "type": "text",
                "text": "The existing runtime request is still in progress. Poll this same request again; do not resubmit the user message.",
            }],
            "structuredContent": {
                "ok": True,
                "action": "poll_runtime",
                "request_id": request_id,
                "daemon_request_id": request_id,
                "resume_tool": "jazn_resume_visible_reply",
                "must_not_resubmit_user_message": True,
                "recovered_existing_request": True,
            },
            "_meta": {
                "transport": "secure_loopback_gateway",
                "recovery": "existing_daemon_request",
            },
            "isError": False,
        }

    if action != "generate_then_finalize":
        reason = str(
            presentation.get("reason")
            or presentation.get("diagnostic_reason")
            or runtime_result.get("error_code")
            or envelope.get("error_code")
            or "runtime_host_diagnostic_required_after_recovery"
        )
        return _tool_error(reason, response=envelope)

    try:
        record = recover_pending_host_request(
            Path(root),
            daemon_request_id=request_id,
            turn_id=turn_id,
            request_contract_hash=host_request_contract_hash,
        )
        _validate_runtime_binding(
            daemon_request_id=request_id,
            record=record,
            presentation=presentation,
            runtime_result=runtime_result,
        )
        continuation = reissue_pending_continuation(Path(root), record)
    except HostRequestStoreError as exc:
        return _tool_error(str(exc), response=envelope)

    binding_value = record.get("binding")
    binding = dict(binding_value) if isinstance(binding_value, Mapping) else {}
    generation_value = record.get("generation_context")
    generation = dict(generation_value) if isinstance(generation_value, Mapping) else {}
    host_policy_value = generation.get("host_generation_policy")
    host_policy = dict(host_policy_value) if isinstance(host_policy_value, Mapping) else {}
    host_context_value = generation.get("host_generation_context")
    host_context = dict(host_context_value) if isinstance(host_context_value, Mapping) else {}

    return {
        "content": [{
            "type": "text",
            "text": "Resume the interrupted host-generation phase from this existing contract, then call jazn_finalize_reply. Do not resubmit the user message and do not display this intermediate result.",
        }],
        "structuredContent": {
            "ok": True,
            "action": "generate_then_finalize",
            "continuation_token": continuation["continuation_token"],
            "expires_at_utc": continuation.get("expires_at_utc"),
            "turn_id": continuation.get("turn_id") or binding.get("turn_id"),
            "trace_id": continuation.get("trace_id") or binding.get("trace_id"),
            "host_request_contract_hash": continuation.get("request_contract_hash"),
            "required_visible_prefix": generation.get("required_visible_prefix"),
            "host_generation_policy": host_policy,
            "host_generation_context": host_context,
            "host_generation_rules": list(generation.get("host_generation_rules") or []),
            "daemon_request_id": request_id,
            "finalization_tool": "jazn_finalize_reply",
            "resume_tool": "jazn_resume_visible_reply",
            "must_not_display_intermediate": True,
            "must_not_resubmit_user_message": True,
            "recovered_existing_request": True,
            "continuation_token_reissued_idempotently": True,
        },
        "_meta": {
            "transport": "secure_loopback_gateway",
            "phase": "host_visible_generation_requested",
            "runtime_response_redacted": True,
            "recovery": "existing_pending_phase_1",
        },
        "isError": False,
    }
