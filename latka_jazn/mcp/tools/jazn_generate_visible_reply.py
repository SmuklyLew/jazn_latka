from __future__ import annotations

from typing import Any, Protocol, cast

from latka_jazn.bridge.secure_host_runtime_gateway import GatewayError
from latka_jazn.core.chatgpt_host_pre_response_gate import (
    build_host_pre_response_gate_telemetry,
    run_host_pre_response_gate,
)
from latka_jazn.core.memory_recall_observability import correlate_memory_recall_transport


class HostRuntimeGateway(Protocol):
    """Structural contract required by the visible-reply MCP tool."""

    def chat(
        self,
        message: str,
        /,
        *,
        session_id: str | None = None,
        request_id: str | None = None,
    ) -> dict[str, Any]: ...

    def issue_continuation(self, response: dict[str, Any], /) -> dict[str, Any]: ...


def _object_or_none(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return cast(dict[str, Any], value)
    return None


def _presentation_from(response: dict[str, Any]) -> dict[str, Any]:
    nested = _object_or_none(response.get("chatgpt_host_presentation"))
    if nested is not None:
        return nested
    if str(response.get("type") or "") == "chatgpt_host_presentation" or response.get("action"):
        return response
    return {}


def _tool_error(
    reason: str,
    *,
    response: dict[str, Any] | None = None,
    gate_telemetry: dict[str, Any] | None = None,
    memory_recall_observability: dict[str, Any] | None = None,
) -> dict[str, Any]:
    structured: dict[str, Any] = {
        "ok": False,
        "action": "host_diagnostic",
        "reason": reason,
        "visible_output_source": "host_diagnostic",
    }
    if gate_telemetry is not None:
        structured["host_pre_response_gate"] = gate_telemetry
    if memory_recall_observability:
        structured["memory_recall_observability"] = memory_recall_observability
    return {
        "content": [{"type": "text", "text": f"Jaźń runtime did not produce a displayable result: {reason}."}],
        "structuredContent": structured,
        "_meta": {"runtime_response": response or {}},
        "isError": True,
    }


def _diagnostic_gate_telemetry(
    *,
    reason: str,
    message: str,
    requested_runtime_root: object,
    runtime_turn_invoked: bool,
    response: dict[str, Any] | None = None,
) -> dict[str, Any]:
    telemetry = build_host_pre_response_gate_telemetry(
        presentation={
            "type": "chatgpt_host_presentation",
            "action": "host_diagnostic",
            "phase": "host_diagnostic_required",
            "diagnostic_reason": reason,
        },
        response=response,
        user_text=message,
        requested_runtime_root=str(requested_runtime_root or ""),
        runtime_turn_invoked=runtime_turn_invoked,
        visible_output_source="host_diagnostic",
        turn_ingress_gate_enforced=True,
    )
    if telemetry["fallback_reason"] == "runtime_transport_not_reported":
        telemetry["fallback_reason"] = reason
    return telemetry


def _memory_recall_observability(
    presentation: dict[str, Any],
    response: dict[str, Any],
    gate_telemetry: dict[str, Any],
) -> dict[str, Any]:
    bridge = _object_or_none(presentation.get("chatgpt_host_bridge")) or {}
    for container in (presentation, response, bridge):
        observability = _object_or_none(container.get("memory_recall_observability"))
        if observability:
            return correlate_memory_recall_transport(observability, gate_telemetry)
    return {}


def run(
    gateway: HostRuntimeGateway,
    *,
    message: str,
    session_id: str | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    """Route one MCP-visible ChatGPT message through the canonical ingress gate.

    `request_id` is the daemon-side side-effect identity allocated by the MCP
    server before dispatch. It is propagated unchanged through the gateway so a
    lost transport response can only be resumed, never recreated as a new turn.
    Direct legacy/test callers that omit the id retain the historical gateway
    call shape; production MCP always allocates the id before this function.
    """

    requested_runtime_root = getattr(gateway, "runtime_root", None)

    def invoke_runtime(exact_text: str) -> dict[str, Any]:
        if request_id is None:
            return gateway.chat(exact_text, session_id=session_id)
        return gateway.chat(
            exact_text,
            session_id=session_id,
            request_id=request_id,
        )

    gate_result = run_host_pre_response_gate(
        message,
        invoke_runtime=invoke_runtime,
        requested_runtime_root=str(requested_runtime_root or ""),
    )
    gate_telemetry = _object_or_none(gate_result.get("host_pre_response_gate")) or {}
    memory_observability = _object_or_none(gate_result.get("memory_recall_observability")) or {}

    if str(gate_result.get("action") or "") == "host_diagnostic":
        reason = str(gate_result.get("diagnostic_reason") or "runtime_host_diagnostic_required")
        return _tool_error(
            reason,
            gate_telemetry=gate_telemetry,
            memory_recall_observability=memory_observability,
        )

    response = _object_or_none(gate_result.get("runtime_response")) or {}
    presentation = _object_or_none(gate_result.get("runtime_presentation")) or _presentation_from(response)
    action = str(gate_result.get("action") or presentation.get("action") or "host_diagnostic")
    turn_id = presentation.get("turn_id")
    trace_id = presentation.get("trace_id")
    if not memory_observability:
        memory_observability = _memory_recall_observability(
            presentation,
            response,
            gate_telemetry,
        )
    bridge = (
        _object_or_none(presentation.get("chatgpt_host_bridge"))
        or _object_or_none(response.get("chatgpt_host_bridge"))
        or {}
    )

    if action == "display_exact":
        final_text = str(gate_result.get("visible_text") or "")
        checks = _object_or_none(presentation.get("runtime_checks")) or {}
        integrity = _object_or_none(response.get("final_visible_integrity"))
        if integrity is None:
            final_contract = _object_or_none(response.get("final_response_contract")) or {}
            integrity = _object_or_none(final_contract.get("final_visible_integrity")) or {}
        integrity_valid = integrity.get("valid") is True or checks.get("final_visible_integrity_valid") is True
        truth_ok = checks.get("runtime_truth_gate_ok")
        if truth_ok is None:
            truth_gate = response.get("runtime_truth_gate")
            truth_ok = truth_gate.get("ok") if isinstance(truth_gate, dict) else None
        if not final_text or integrity_valid is not True or truth_ok is not True:
            reason = "validated_final_visible_text_missing"
            return _tool_error(
                reason,
                response=response,
                gate_telemetry=_diagnostic_gate_telemetry(
                    reason=reason,
                    message=message,
                    requested_runtime_root=requested_runtime_root,
                    runtime_turn_invoked=True,
                    response=response,
                ),
            )
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
                "visible_output_source": gate_telemetry.get("visible_output_source"),
                "host_pre_response_gate": gate_telemetry,
                "turn_ingress_gate_enforced": True,
                "host_route_bound": bool(gate_telemetry.get("host_route_bound")),
                **(
                    {"memory_recall_observability": memory_observability}
                    if memory_observability
                    else {}
                ),
            },
            "_meta": {
                "transport": "secure_loopback_gateway",
                "phase": presentation.get("phase"),
                "ingress_gate": "chatgpt_host_pre_response_gate",
            },
            "isError": False,
        }

    if action == "generate_then_finalize":
        try:
            continuation = gateway.issue_continuation(response)
        except GatewayError as exc:
            reason = f"continuation_issue_failed:{exc}"
            return _tool_error(
                reason,
                response=response,
                gate_telemetry=_diagnostic_gate_telemetry(
                    reason=reason,
                    message=message,
                    requested_runtime_root=requested_runtime_root,
                    runtime_turn_invoked=True,
                    response=response,
                ),
            )
        host_policy = _object_or_none(bridge.get("host_generation_policy")) or {}
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
                "host_generation_context": _object_or_none(bridge.get("host_generation_context")) or {},
                "host_generation_rules": list(bridge.get("host_generation_rules") or []),
                "daemon_request_id": bridge.get("daemon_request_id") or request_id,
                "finalization_tool": "jazn_finalize_reply",
                "must_not_display_intermediate": True,
                "visible_output_source": None,
                "host_pre_response_gate": gate_telemetry,
                "turn_ingress_gate_enforced": True,
                "host_route_bound": bool(gate_telemetry.get("host_route_bound")),
                **(
                    {"memory_recall_observability": memory_observability}
                    if memory_observability
                    else {}
                ),
            },
            "_meta": {
                "transport": "secure_loopback_gateway",
                "phase": presentation.get("phase"),
                "runtime_response_redacted": True,
                "ingress_gate": "chatgpt_host_pre_response_gate",
            },
            "isError": False,
        }

    if action == "poll_runtime":
        daemon_request_id = (
            presentation.get("daemon_request_id")
            or presentation.get("request_id")
            or response.get("request_id")
            or request_id
        )
        poll_command = presentation.get("poll_command") or "jazn_resume_visible_reply"
        if not daemon_request_id:
            reason = "poll_contract_missing"
            return _tool_error(
                reason,
                response=response,
                gate_telemetry=_diagnostic_gate_telemetry(
                    reason=reason,
                    message=message,
                    requested_runtime_root=requested_runtime_root,
                    runtime_turn_invoked=True,
                    response=response,
                ),
            )
        return {
            "content": [{"type": "text", "text": "The runtime turn is still in progress. Poll the existing request; do not resubmit the user message."}],
            "structuredContent": {
                "ok": True,
                "action": "poll_runtime",
                "request_id": daemon_request_id,
                "daemon_request_id": daemon_request_id,
                "poll_command": poll_command,
                "resume_tool": "jazn_resume_visible_reply",
                "must_not_resubmit_user_message": True,
                "submit_outcome_authoritative": presentation.get("submit_outcome_authoritative"),
                "turn_id": turn_id,
                "trace_id": trace_id,
                "visible_output_source": None,
                "host_pre_response_gate": gate_telemetry,
                "turn_ingress_gate_enforced": True,
                "host_route_bound": bool(gate_telemetry.get("host_route_bound")),
                **(
                    {"memory_recall_observability": memory_observability}
                    if memory_observability
                    else {}
                ),
            },
            "_meta": {
                "transport": "secure_loopback_gateway",
                "ingress_gate": "chatgpt_host_pre_response_gate",
                "recovery": "same_daemon_request_id",
            },
            "isError": False,
        }

    return _tool_error(
        "unsupported_gate_action",
        response=response,
        gate_telemetry=gate_telemetry,
        memory_recall_observability=memory_observability,
    )
