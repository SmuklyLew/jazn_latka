from __future__ import annotations

from os import PathLike
from typing import Any

from latka_jazn.core.memory_intent_contract import analyze_memory_intent
from latka_jazn.core.memory_recall_observability import memory_recall_truth_boundary_violation

from ._core import (
    HOST_ROUTING_BYPASS,
    HostCandidateGenerator,
    RuntimeCandidateFinalizer,
    RuntimeInvoker,
    _attach_voice_e2e_verification,
    _diagnostic_result,
    _enforce_persistent_voice_e2e,
    _mapping,
    _memory_recall_from,
    _presentation_from,
    build_host_pre_response_gate_telemetry,
)


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
    except (ConnectionError, TimeoutError, OSError, RuntimeError, TypeError, ValueError) as exc:
        detail = str(exc).strip()
        return _diagnostic_result(
            user_text=exact_user_text,
            requested_runtime_root=requested_runtime_root,
            error_code="RUNTIME_UNAVAILABLE",
            diagnostic_reason=(
                f"runtime_unavailable:{detail}" if detail else "runtime_unavailable"
            ),
            runtime_turn_invoked=True,
        )
    presentation = _presentation_from(runtime_response)
    action = str(presentation.get("action") or "")
    memory_recall_observability = _memory_recall_from(presentation, runtime_response)
    recall_required = analyze_memory_intent(exact_user_text).content_requested
    memory_violation = memory_recall_truth_boundary_violation(
        memory_recall_observability,
        recall_required=recall_required,
        expected_turn_id=str(
            presentation.get("turn_id")
            or _mapping(presentation.get("chatgpt_host_bridge")).get("turn_id")
            or ""
        )
        or None,
        expected_trace_id=str(
            presentation.get("trace_id")
            or _mapping(presentation.get("chatgpt_host_bridge")).get("trace_id")
            or ""
        )
        or None,
    )
    if memory_violation is not None:
        return _diagnostic_result(
            user_text=exact_user_text,
            requested_runtime_root=requested_runtime_root,
            error_code="MEMORY_RECALL_TRUTH_BOUNDARY_FAILED",
            diagnostic_reason=memory_violation,
            runtime_turn_invoked=True,
            response=runtime_response,
            memory_recall_observability=memory_recall_observability,
        )

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
            turn_ingress_gate_enforced=True,
            visible_output_source=(
                "runtime_finalized"
                if presentation.get("phase") == "host_visible_reply_recorded"
                else "runtime_exact"
            ),
        )
        result = {
            "ok": True,
            "action": "display_exact",
            "visible_text": final_text,
            "visible_output_source": telemetry["visible_output_source"],
            "host_pre_response_gate": telemetry,
            "turn_ingress_gate_enforced": True,
            "host_route_bound": bool(telemetry.get("host_route_bound")),
            "runtime_presentation": presentation,
            "runtime_response": runtime_response,
        }
        if memory_recall_observability:
            result["memory_recall_observability"] = memory_recall_observability
        return _enforce_persistent_voice_e2e(
            result,
            exact_user_text=exact_user_text,
            requested_runtime_root=requested_runtime_root,
        )

    if action == "generate_then_finalize":
        if generate_host_candidate is None or finalize_runtime_candidate is None:
            telemetry = build_host_pre_response_gate_telemetry(
                presentation=presentation,
                response=runtime_response,
                user_text=exact_user_text,
                requested_runtime_root=requested_runtime_root,
                runtime_turn_invoked=True,
                turn_ingress_gate_enforced=True,
                visible_output_source=None,
                finalization_completed=False,
            )
            result = {
                "ok": True,
                "action": "generate_then_finalize",
                "visible_text": "",
                "visible_output_source": None,
                "host_pre_response_gate": telemetry,
                "turn_ingress_gate_enforced": True,
                "host_route_bound": bool(telemetry.get("host_route_bound")),
                "runtime_presentation": presentation,
                "runtime_response": runtime_response,
            }
            if memory_recall_observability:
                result["memory_recall_observability"] = memory_recall_observability
            return _attach_voice_e2e_verification(
                result,
                exact_user_text=exact_user_text,
            )
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
            turn_ingress_gate_enforced=True,
            visible_output_source="runtime_finalized",
            finalization_completed=True,
        )
        result = {
            "ok": True,
            "action": "display_exact",
            "visible_text": final_text,
            "visible_output_source": "runtime_finalized",
            "host_pre_response_gate": telemetry,
            "turn_ingress_gate_enforced": True,
            "host_route_bound": bool(telemetry.get("host_route_bound")),
            "runtime_presentation": finalized_presentation,
            "runtime_response": finalized_response,
        }
        if memory_recall_observability:
            result["memory_recall_observability"] = memory_recall_observability
        return _enforce_persistent_voice_e2e(
            result,
            exact_user_text=exact_user_text,
            requested_runtime_root=requested_runtime_root,
        )

    if action == "poll_runtime":
        telemetry = build_host_pre_response_gate_telemetry(
            presentation=presentation,
            response=runtime_response,
            user_text=exact_user_text,
            requested_runtime_root=requested_runtime_root,
            runtime_turn_invoked=True,
            turn_ingress_gate_enforced=True,
            visible_output_source=None,
        )
        result = {
            "ok": True,
            "action": "poll_runtime",
            "visible_text": "",
            "visible_output_source": None,
            "host_pre_response_gate": telemetry,
            "turn_ingress_gate_enforced": True,
            "host_route_bound": bool(telemetry.get("host_route_bound")),
            "runtime_presentation": presentation,
            "runtime_response": runtime_response,
        }
        if memory_recall_observability:
            result["memory_recall_observability"] = memory_recall_observability
        return _attach_voice_e2e_verification(
            result,
            exact_user_text=exact_user_text,
        )

    if action == "host_diagnostic":
        bridge = _mapping(presentation.get("chatgpt_host_bridge"))
        reason = str(
            presentation.get("diagnostic_reason")
            or presentation.get("reason")
            or bridge.get("diagnostic_reason")
            or "runtime_host_diagnostic_required"
        )
        return _diagnostic_result(
            user_text=exact_user_text,
            requested_runtime_root=requested_runtime_root,
            error_code="RUNTIME_HOST_DIAGNOSTIC",
            diagnostic_reason=reason,
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
