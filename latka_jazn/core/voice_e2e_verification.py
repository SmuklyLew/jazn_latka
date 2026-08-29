from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import os
from pathlib import Path
from typing import Any, Mapping

from latka_jazn.version import schema_version


@dataclass(frozen=True, slots=True)
class VoiceE2EVerification:
    exact_user_turn_bound: bool
    pre_response_gate_passed: bool
    persistent_runtime_used: bool
    daemon_identity_verified: bool
    daemon_pid: int | None
    subject_root: str | None
    subject_root_matches_endpoint: bool
    runtime_turn_id: str | None
    trace_id: str | None
    turn_trace_bound: bool
    presentation_accepted: bool
    finalization_completed_when_required: bool
    exact_final_visible_text: bool
    visible_output_source: str | None
    author_source: str | None
    author_is_jazn_runtime: bool
    blocking_reasons: tuple[str, ...]

    @property
    def verified(self) -> bool:
        return not self.blocking_reasons

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["voice_e2e_verified"] = self.verified
        payload["scope"] = "current_turn_only"
        payload["schema_version"] = schema_version("voice_e2e_verification")
        payload["truth_boundary"] = (
            "This proof belongs only to the exact current turn. It does not prove "
            "that a later turn or a currently stopped daemon is ready."
        )
        return payload


def _mapping(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _same_runtime_path(left: object, right: object) -> bool:
    if left in (None, "") or right in (None, ""):
        return False
    try:
        left_path = os.path.normcase(str(Path(str(left)).expanduser().resolve()))
        right_path = os.path.normcase(str(Path(str(right)).expanduser().resolve()))
    except (OSError, RuntimeError, ValueError):
        return False
    return left_path == right_path


def _positive_pid(value: object) -> int | None:
    try:
        pid = int(value)
    except (TypeError, ValueError):
        return None
    return pid if pid > 0 else None


def evaluate_voice_e2e_verification(
    *,
    exact_user_text: str,
    gate_result: Mapping[str, Any],
) -> VoiceE2EVerification:
    """Verify one completed visible turn without creating persistent readiness."""

    result = dict(gate_result)
    gate = _mapping(result.get("host_pre_response_gate"))
    presentation = _mapping(result.get("runtime_presentation"))
    response = _mapping(result.get("runtime_response"))
    bridge = _mapping(presentation.get("chatgpt_host_bridge"))
    transport = _mapping(presentation.get("transport_observability"))
    if not transport:
        transport = _mapping(response.get("transport_observability"))
    final_contract = _mapping(response.get("final_response_contract"))
    if not final_contract:
        final_contract = _mapping(presentation.get("final_response_contract"))

    user_digest = hashlib.sha256(str(exact_user_text).encode("utf-8")).hexdigest()
    turn_id = str(
        gate.get("runtime_turn_id")
        or presentation.get("turn_id")
        or bridge.get("turn_id")
        or ""
    ).strip()
    trace_id = str(
        gate.get("trace_id")
        or presentation.get("trace_id")
        or bridge.get("trace_id")
        or ""
    ).strip()
    visible_source = str(
        result.get("visible_output_source")
        or gate.get("visible_output_source")
        or ""
    ).strip()
    author_source = str(
        presentation.get("author_source")
        or final_contract.get("author_source")
        or bridge.get("author_source")
        or ""
    ).strip()
    resolved_root = (
        transport.get("resolved_active_root")
        or gate.get("resolved_active_root")
    )
    endpoint_root = transport.get("daemon_endpoint_root")
    daemon_pid = _positive_pid(transport.get("daemon_pid"))
    final_text = str(result.get("visible_text") or "")
    runtime_final_text = str(
        presentation.get("final_visible_text")
        or response.get("final_visible_text")
        or ""
    )
    finalization_required = bool(
        gate.get("finalization_required") is True
        or visible_source == "runtime_finalized"
    )
    finalization_completed = gate.get("finalization_completed") is True

    checks = {
        "exact_user_turn_not_bound": bool(
            gate.get("runtime_turn_invoked") is True
            and gate.get("user_text_sha256") == user_digest
        ),
        "pre_response_gate_not_passed": bool(
            gate.get("host_pre_response_gate") is True
            and gate.get("host_routing_bypass_detected") is not True
        ),
        "persistent_runtime_not_used": (
            transport.get("selected_transport") == "persistent_daemon"
        ),
        "daemon_identity_not_verified": bool(
            transport.get("daemon_identity_verified") is True
            and daemon_pid is not None
        ),
        "subject_root_not_bound": bool(
            resolved_root
            and _same_runtime_path(resolved_root, endpoint_root)
        ),
        "turn_trace_not_bound": bool(turn_id and trace_id),
        "presentation_not_accepted": bool(
            result.get("ok") is True
            and result.get("action") == "display_exact"
            and visible_source in {"runtime_exact", "runtime_finalized"}
        ),
        "required_finalization_not_completed": bool(
            not finalization_required or finalization_completed
        ),
        "final_visible_text_not_exact": bool(
            final_text and runtime_final_text and final_text == runtime_final_text
        ),
        "author_source_not_jazn_runtime": author_source == "jazn_runtime",
    }
    return VoiceE2EVerification(
        exact_user_turn_bound=checks["exact_user_turn_not_bound"],
        pre_response_gate_passed=checks["pre_response_gate_not_passed"],
        persistent_runtime_used=checks["persistent_runtime_not_used"],
        daemon_identity_verified=checks["daemon_identity_not_verified"],
        daemon_pid=daemon_pid,
        subject_root=str(resolved_root) if resolved_root else None,
        subject_root_matches_endpoint=checks["subject_root_not_bound"],
        runtime_turn_id=turn_id or None,
        trace_id=trace_id or None,
        turn_trace_bound=checks["turn_trace_not_bound"],
        presentation_accepted=checks["presentation_not_accepted"],
        finalization_completed_when_required=checks[
            "required_finalization_not_completed"
        ],
        exact_final_visible_text=checks["final_visible_text_not_exact"],
        visible_output_source=visible_source or None,
        author_source=author_source or None,
        author_is_jazn_runtime=checks["author_source_not_jazn_runtime"],
        blocking_reasons=tuple(reason for reason, passed in checks.items() if not passed),
    )


__all__ = ["VoiceE2EVerification", "evaluate_voice_e2e_verification"]
