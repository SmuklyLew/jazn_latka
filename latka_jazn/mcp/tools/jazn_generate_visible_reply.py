from __future__ import annotations

from typing import Any

from latka_jazn.bridge.secure_host_runtime_gateway import GatewayError, SecureHostRuntimeGateway


def _presentation_from(response: dict[str, Any]) -> dict[str, Any]:
    nested = response.get("chatgpt_host_presentation")
    if isinstance(nested, dict):
        return nested
    if str(response.get("type") or "") == "chatgpt_host_presentation" or response.get("action"):
        return response
    return {}


def _tool_error(reason: str, *, response: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "content": [{"type": "text", "text": f"Jaźń runtime did not produce a displayable result: {reason}."}],
        "structuredContent": {"ok": False, "action": "host_diagnostic", "reason": reason},
        "_meta": {"runtime_response": response or {}},
        "isError": True,
    }


def run(
    gateway: SecureHostRuntimeGateway,
    *,
    message: str,
    session_id: str | None = None,
) -> dict[str, Any]:
    response = gateway.chat(message, session_id=session_id)
    presentation = _presentation_from(response)
    action = str(presentation.get("action") or "host_diagnostic")
    turn_id = presentation.get("turn_id")
    trace_id = presentation.get("trace_id")

    if action == "display_exact":
        final_text = str(presentation.get("final_visible_text") or response.get("final_visible_text") or "")
        checks = presentation.get("runtime_checks") if isinstance(presentation.get("runtime_checks"), dict) else {}
        integrity = response.get("final_visible_integrity")
        if not isinstance(integrity, dict):
            final_contract = response.get("final_response_contract")
            integrity = final_contract.get("final_visible_integrity", {}) if isinstance(final_contract, dict) else {}
        integrity_valid = integrity.get("valid") is True or checks.get("final_visible_integrity_valid") is True
        truth_ok = checks.get("runtime_truth_gate_ok")
        if truth_ok is None:
            truth_gate = response.get("runtime_truth_gate")
            truth_ok = truth_gate.get("ok") if isinstance(truth_gate, dict) else None
        if not final_text or integrity_valid is not True or truth_ok is not True:
            return _tool_error("validated_final_visible_text_missing", response=response)
        return {
            "content": [{"type": "text", "text": final_text}],
            "structuredContent": {
                "ok": True,
                "action": "display_exact",
                "final_visible_text": final_text,
                "final_text_sha256": presentation.get("final_text_sha256"),
                "turn_id": turn_id,
                "trace_id": trace_id,
                "must_display_exactly": True,
            },
            "_meta": {"transport": "secure_loopback_gateway", "phase": presentation.get("phase")},
            "isError": False,
        }

    if action == "generate_then_finalize":
        try:
            continuation = gateway.issue_continuation(response)
        except GatewayError as exc:
            return _tool_error(f"continuation_issue_failed:{exc}", response=response)
        bridge = presentation.get("chatgpt_host_bridge")
        if not isinstance(bridge, dict):
            bridge = response.get("chatgpt_host_bridge") if isinstance(response.get("chatgpt_host_bridge"), dict) else {}
        host_policy = bridge.get("host_generation_policy") if isinstance(bridge.get("host_generation_policy"), dict) else {}
        host_model_context = bridge.get("host_model_context") if isinstance(bridge.get("host_model_context"), dict) else {}
        if not host_model_context:
            return _tool_error("host_model_context_missing", response=response)
        return {
            "content": [{
                "type": "text",
                "text": "Generate the reply only from the supplied host generation contract, then call jazn_finalize_reply with the continuation token. Do not display this intermediate result.",
            }],
            "structuredContent": {
                "ok": True,
                "action": "generate_then_finalize",
                "continuation_token": continuation["continuation_token"],
                "expires_at_utc": continuation.get("expires_at_utc"),
                "turn_id": continuation.get("turn_id") or turn_id,
                "trace_id": continuation.get("trace_id") or trace_id,
                "host_request_contract_hash": continuation.get("request_contract_hash"),
                "required_visible_prefix": presentation.get("required_visible_prefix"),
                "host_generation_policy": host_policy,
                "host_generation_rules": list(bridge.get("host_generation_rules") or []),
                "host_model_context": host_model_context,
                "finalization_tool": "jazn_finalize_reply",
                "finalization_arguments": {
                    "continuation_token": "Use the opaque token returned above.",
                    "final_text": "Return only the candidate reply body, without adding a timestamp envelope.",
                    "final_text_sha256": "SHA-256 of canonical UTF-8/LF final_text.",
                    "used_memory_item_ids": "Declare only IDs actually used from allowed_memory_item_ids; otherwise [].",
                },
                "must_not_display_intermediate": True,
            },
            "_meta": {
                "transport": "secure_loopback_gateway",
                "phase": presentation.get("phase"),
                "runtime_response_redacted": True,
            },
            "isError": False,
        }

    if action == "poll_runtime":
        request_id = presentation.get("daemon_request_id") or presentation.get("request_id")
        poll_command = presentation.get("poll_command")
        if not request_id or not poll_command:
            return _tool_error("poll_contract_missing", response=response)
        return {
            "content": [{"type": "text", "text": "The runtime turn is still in progress. Poll the existing request; do not resubmit the user message."}],
            "structuredContent": {
                "ok": True,
                "action": "poll_runtime",
                "request_id": request_id,
                "poll_command": poll_command,
                "turn_id": turn_id,
                "trace_id": trace_id,
            },
            "_meta": {"transport": "secure_loopback_gateway"},
            "isError": False,
        }

    reason = str(
        presentation.get("reason")
        or presentation.get("diagnostic_reason")
        or (presentation.get("chatgpt_host_bridge") or {}).get("diagnostic_reason")
        or "runtime_host_diagnostic_required"
    )
    return _tool_error(reason, response=response)
