from __future__ import annotations

from collections.abc import Callable, Mapping
import hashlib
from os import PathLike
import re
from typing import Any

from latka_jazn.version import schema_version


HOST_ROUTING_BYPASS = "HOST_ROUTING_BYPASS"
HOST_PRE_RESPONSE_GATE_VERSION = schema_version("chatgpt_host_pre_response_gate")
VISIBLE_OUTPUT_SOURCES = frozenset({"runtime_exact", "runtime_finalized", "host_diagnostic"})

RuntimeInvoker = Callable[[str], Mapping[str, Any]]
HostCandidateGenerator = Callable[[dict[str, Any]], str]
RuntimeCandidateFinalizer = Callable[[str, dict[str, Any]], Mapping[str, Any]]


def _user_text_sha256(user_text: str) -> str:
    return hashlib.sha256(str(user_text).encode("utf-8")).hexdigest()


def _mapping(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _presentation_from(response: Mapping[str, Any]) -> dict[str, Any]:
    nested = _mapping(response.get("chatgpt_host_presentation"))
    if nested:
        return nested
    if response.get("action") is not None or response.get("type") == "chatgpt_host_presentation":
        return dict(response)
    return {}


def _transport_from(
    presentation: Mapping[str, Any],
    response: Mapping[str, Any] | None,
) -> dict[str, Any]:
    response_map = dict(response or {})
    bridge = _mapping(presentation.get("chatgpt_host_bridge"))
    chat_bridge = _mapping(response_map.get("chat_bridge"))
    for container in (presentation, response_map, bridge, chat_bridge):
        transport = _mapping(container.get("transport_observability"))
        if transport:
            return transport
    return {}


def build_host_pre_response_gate_telemetry(
    *,
    presentation: Mapping[str, Any],
    response: Mapping[str, Any] | None = None,
    user_text: str = "",
    user_text_sha256: str | None = None,
    requested_runtime_root: str | PathLike[str] | None = None,
    runtime_turn_invoked: bool,
    visible_output_source: str | None = None,
    bypass_detected: bool = False,
    bypass_reason: str | None = None,
    finalization_completed: bool | None = None,
) -> dict[str, Any]:
    presentation_map = dict(presentation)
    response_map = dict(response or {})
    bridge = _mapping(presentation_map.get("chatgpt_host_bridge"))
    transport = _transport_from(presentation_map, response_map)
    action = str(presentation_map.get("action") or "host_diagnostic")
    phase = str(presentation_map.get("phase") or bridge.get("phase") or "")
    if visible_output_source is None:
        if action == "display_exact":
            visible_output_source = (
                "runtime_finalized"
                if phase == "host_visible_reply_recorded"
                else "runtime_exact"
            )
        elif action == "host_diagnostic":
            visible_output_source = "host_diagnostic"
    if visible_output_source is not None and visible_output_source not in VISIBLE_OUTPUT_SOURCES:
        raise ValueError(f"illegal visible output source: {visible_output_source}")
    finalization_required = bool(
        action == "generate_then_finalize"
        or phase == "host_visible_generation_requested"
    )
    if finalization_completed is None:
        finalization_completed = bool(
            action == "display_exact" and phase == "host_visible_reply_recorded"
        )
    supplied_digest = str(user_text_sha256 or bridge.get("user_text_sha256") or "").lower()
    digest = (
        supplied_digest
        if re.fullmatch(r"[0-9a-f]{64}", supplied_digest)
        else _user_text_sha256(user_text)
    )
    requested_root = str(
        requested_runtime_root
        or transport.get("requested_runtime_root")
        or response_map.get("requested_runtime_root")
        or ""
    )
    resolved_root = (
        transport.get("resolved_active_root")
        or response_map.get("resolved_active_root")
        or bridge.get("resolved_active_root")
    )
    return {
        "host_pre_response_gate": True,
        "host_pre_response_gate_version": HOST_PRE_RESPONSE_GATE_VERSION,
        "runtime_turn_invoked": bool(runtime_turn_invoked),
        "runtime_turn_id": presentation_map.get("turn_id") or bridge.get("turn_id"),
        "trace_id": presentation_map.get("trace_id") or bridge.get("trace_id"),
        "user_text_sha256": digest,
        "requested_runtime_root": requested_root,
        "resolved_active_root": str(resolved_root) if resolved_root else None,
        "presentation_action": action,
        "finalization_required": finalization_required,
        "finalization_completed": bool(finalization_completed),
        "visible_output_source": visible_output_source,
        "host_routing_bypass_detected": bypass_detected,
        "host_routing_bypass_reason": bypass_reason,
        "selected_transport": str(
            transport.get("selected_transport")
            or ("host_diagnostic" if action == "host_diagnostic" else "unknown")
        ),
        "fallback_reason": str(
            transport.get("fallback_reason")
            or bypass_reason
            or ("runtime_transport_not_reported" if runtime_turn_invoked else "runtime_not_invoked")
        ),
    }


def _diagnostic_result(
    *,
    user_text: str,
    requested_runtime_root: str | PathLike[str] | None,
    error_code: str,
    diagnostic_reason: str,
    runtime_turn_invoked: bool,
    response: Mapping[str, Any] | None = None,
    bypass_detected: bool = False,
    bypass_reason: str | None = None,
) -> dict[str, Any]:
    presentation = {
        "type": "chatgpt_host_presentation",
        "action": "host_diagnostic",
        "phase": "host_diagnostic_required",
        "diagnostic_reason": diagnostic_reason,
    }
    telemetry = build_host_pre_response_gate_telemetry(
        presentation=presentation,
        response=response,
        user_text=user_text,
        requested_runtime_root=requested_runtime_root,
        runtime_turn_invoked=runtime_turn_invoked,
        visible_output_source="host_diagnostic",
        bypass_detected=bypass_detected,
        bypass_reason=bypass_reason,
    )
    if not telemetry.get("fallback_reason") or telemetry["fallback_reason"] == "runtime_transport_not_reported":
        telemetry["fallback_reason"] = diagnostic_reason
    return {
        "ok": False,
        "action": "host_diagnostic",
        "error_code": error_code,
        "diagnostic_reason": diagnostic_reason,
        "visible_text": f"Host diagnostic: {diagnostic_reason}.",
        "visible_output_source": "host_diagnostic",
        "host_pre_response_gate": telemetry,
    }


def run_host_pre_response_gate(
    user_text: str,
    *,
    invoke_runtime: RuntimeInvoker,
    generate_host_candidate: HostCandidateGenerator | None = None,
    finalize_runtime_candidate: RuntimeCandidateFinalizer | None = None,
    host_generated_text: str | None = None,
    requested_runtime_root: str | PathLike[str] | None = None,
) -> dict[str, Any]:
    """Run one exact host turn through the canonical runtime presentation path.

    The callback invoke_runtime must be the existing run.py chat-gpt or MCP
    equivalent. The optional finalizer consumes its existing two-phase contract.
    Candidate text is intentionally never included in the returned object.
    """

    exact_user_text = str(user_text)
    if host_generated_text is not None:
        return _diagnostic_result(
            user_text=exact_user_text,
            requested_runtime_root=requested_runtime_root,
            error_code=HOST_ROUTING_BYPASS,
            diagnostic_reason="host_generated_text_before_gate",
            runtime_turn_invoked=False,
            bypass_detected=True,
            bypass_reason="host_generated_text_before_gate",
        )
    if not exact_user_text:
        return _diagnostic_result(
            user_text=exact_user_text,
            requested_runtime_root=requested_runtime_root,
            error_code="EMPTY_HOST_TURN",
            diagnostic_reason="empty_host_turn",
            runtime_turn_invoked=False,
        )
    try:
        runtime_response = dict(invoke_runtime(exact_user_text))
    except (ConnectionError, TimeoutError, OSError, RuntimeError, TypeError, ValueError):
        return _diagnostic_result(
            user_text=exact_user_text,
            requested_runtime_root=requested_runtime_root,
            error_code="RUNTIME_UNAVAILABLE",
            diagnostic_reason="runtime_unavailable",
            runtime_turn_invoked=True,
        )
    presentation = _presentation_from(runtime_response)
    action = str(presentation.get("action") or "")

    if action == "display_exact":
        final_text = str(
            presentation.get("final_visible_text")
            or runtime_response.get("final_visible_text")
            or ""
        )
        if not final_text:
            return _diagnostic_result(
                user_text=exact_user_text,
                requested_runtime_root=requested_runtime_root,
                error_code="RUNTIME_EXACT_TEXT_MISSING",
                diagnostic_reason="runtime_exact_text_missing",
                runtime_turn_invoked=True,
                response=runtime_response,
            )
        telemetry = build_host_pre_response_gate_telemetry(
            presentation=presentation,
            response=runtime_response,
            user_text=exact_user_text,
            requested_runtime_root=requested_runtime_root,
            runtime_turn_invoked=True,
            visible_output_source=(
                "runtime_finalized"
                if presentation.get("phase") == "host_visible_reply_recorded"
                else "runtime_exact"
            ),
        )
        return {
            "ok": True,
            "action": "display_exact",
            "visible_text": final_text,
            "visible_output_source": telemetry["visible_output_source"],
            "host_pre_response_gate": telemetry,
            "runtime_presentation": presentation,
            "runtime_response": runtime_response,
        }

    if action == "generate_then_finalize":
        if generate_host_candidate is None or finalize_runtime_candidate is None:
            telemetry = build_host_pre_response_gate_telemetry(
                presentation=presentation,
                response=runtime_response,
                user_text=exact_user_text,
                requested_runtime_root=requested_runtime_root,
                runtime_turn_invoked=True,
                visible_output_source=None,
                finalization_completed=False,
            )
            return {
                "ok": True,
                "action": "generate_then_finalize",
                "visible_text": "",
                "visible_output_source": None,
                "host_pre_response_gate": telemetry,
                "runtime_presentation": presentation,
                "runtime_response": runtime_response,
            }
        try:
            candidate = str(generate_host_candidate(presentation))
            finalized_response = dict(finalize_runtime_candidate(candidate, presentation))
        except (ConnectionError, TimeoutError, OSError, RuntimeError, TypeError, ValueError):
            return _diagnostic_result(
                user_text=exact_user_text,
                requested_runtime_root=requested_runtime_root,
                error_code="RUNTIME_FINALIZATION_FAILED",
                diagnostic_reason="runtime_finalization_failed",
                runtime_turn_invoked=True,
                response=runtime_response,
            )
        finalized_presentation = _presentation_from(finalized_response)
        if str(finalized_presentation.get("action") or "") != "display_exact":
            return _diagnostic_result(
                user_text=exact_user_text,
                requested_runtime_root=requested_runtime_root,
                error_code="RUNTIME_FINALIZATION_REJECTED",
                diagnostic_reason="runtime_finalization_rejected",
                runtime_turn_invoked=True,
                response=runtime_response,
            )
        final_text = str(
            finalized_presentation.get("final_visible_text")
            or finalized_response.get("final_visible_text")
            or ""
        )
        if not final_text:
            return _diagnostic_result(
                user_text=exact_user_text,
                requested_runtime_root=requested_runtime_root,
                error_code="RUNTIME_FINALIZED_TEXT_MISSING",
                diagnostic_reason="runtime_finalized_text_missing",
                runtime_turn_invoked=True,
                response=runtime_response,
            )
        telemetry = build_host_pre_response_gate_telemetry(
            presentation=finalized_presentation,
            response=runtime_response,
            user_text=exact_user_text,
            requested_runtime_root=requested_runtime_root,
            runtime_turn_invoked=True,
            visible_output_source="runtime_finalized",
            finalization_completed=True,
        )
        return {
            "ok": True,
            "action": "display_exact",
            "visible_text": final_text,
            "visible_output_source": "runtime_finalized",
            "host_pre_response_gate": telemetry,
            "runtime_presentation": finalized_presentation,
            "runtime_response": finalized_response,
        }

    if action == "poll_runtime":
        telemetry = build_host_pre_response_gate_telemetry(
            presentation=presentation,
            response=runtime_response,
            user_text=exact_user_text,
            requested_runtime_root=requested_runtime_root,
            runtime_turn_invoked=True,
            visible_output_source=None,
        )
        return {
            "ok": True,
            "action": "poll_runtime",
            "visible_text": "",
            "visible_output_source": None,
            "host_pre_response_gate": telemetry,
            "runtime_presentation": presentation,
            "runtime_response": runtime_response,
        }

    if action == "host_diagnostic":
        return _diagnostic_result(
            user_text=exact_user_text,
            requested_runtime_root=requested_runtime_root,
            error_code="RUNTIME_HOST_DIAGNOSTIC",
            diagnostic_reason="runtime_host_diagnostic_required",
            runtime_turn_invoked=True,
            response=runtime_response,
        )
    return _diagnostic_result(
        user_text=exact_user_text,
        requested_runtime_root=requested_runtime_root,
        error_code="UNKNOWN_PRESENTATION_ACTION",
        diagnostic_reason="unknown_presentation_action",
        runtime_turn_invoked=True,
        response=runtime_response,
    )


__all__ = [
    "HOST_PRE_RESPONSE_GATE_VERSION",
    "HOST_ROUTING_BYPASS",
    "VISIBLE_OUTPUT_SOURCES",
    "build_host_pre_response_gate_telemetry",
    "run_host_pre_response_gate",
]
