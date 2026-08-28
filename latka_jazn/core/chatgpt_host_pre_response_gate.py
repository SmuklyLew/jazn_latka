from __future__ import annotations

from collections.abc import Callable, Mapping
import hashlib
from os import PathLike
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


def _telemetry(
    *,
    user_text: str,
    requested_runtime_root: str | PathLike[str] | None,
    bypass_detected: bool,
    bypass_reason: str | None,
) -> dict[str, Any]:
    return {
        "host_pre_response_gate": True,
        "host_pre_response_gate_version": HOST_PRE_RESPONSE_GATE_VERSION,
        "runtime_turn_invoked": False,
        "runtime_turn_id": None,
        "trace_id": None,
        "user_text_sha256": _user_text_sha256(user_text),
        "requested_runtime_root": str(requested_runtime_root or ""),
        "resolved_active_root": None,
        "presentation_action": "host_diagnostic",
        "finalization_required": False,
        "finalization_completed": False,
        "visible_output_source": "host_diagnostic",
        "host_routing_bypass_detected": bypass_detected,
        "host_routing_bypass_reason": bypass_reason,
        "selected_transport": "host_diagnostic",
        "fallback_reason": bypass_reason or "host_pre_response_gate_not_implemented",
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
    """Fail-closed v16.3.23 contract skeleton.

    Commit A establishes the only public orchestration signature and proves the
    missing behavior with RED tests. Commit B implements invocation and the
    presentation/finalization state machine without adding another ChatGPT
    bridge.
    """

    del invoke_runtime, generate_host_candidate, finalize_runtime_candidate
    bypass_detected = bool(host_generated_text)
    bypass_reason = "host_generated_text_before_gate" if bypass_detected else None
    return {
        "ok": False,
        "action": "host_diagnostic",
        "error_code": HOST_ROUTING_BYPASS if bypass_detected else "HOST_PRE_RESPONSE_GATE_NOT_IMPLEMENTED",
        "visible_text": "Host diagnostic: runtime pre-response gate did not accept this turn.",
        "visible_output_source": "host_diagnostic",
        "host_pre_response_gate": _telemetry(
            user_text=user_text,
            requested_runtime_root=requested_runtime_root,
            bypass_detected=bypass_detected,
            bypass_reason=bypass_reason,
        ),
    }


__all__ = [
    "HOST_PRE_RESPONSE_GATE_VERSION",
    "HOST_ROUTING_BYPASS",
    "VISIBLE_OUTPUT_SOURCES",
    "run_host_pre_response_gate",
]
