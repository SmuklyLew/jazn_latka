from __future__ import annotations

"""Evidence-only ChatGPT ingress negotiation before or after SYSTEM materialization.

The caller/host owns observations; code running *inside* an extracted ZIP
cannot grant tool permissions to the surrounding ChatGPT conversation.
This module neither executes a process nor reads private MEMORY.
"""

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys
from typing import Any, Mapping

from latka_jazn.mcp.chatgpt_toolset import classify_current_message_toolset
from latka_jazn.mcp.remote_runtime import (
    PUBLIC_CONNECTOR_STATUS_SCHEMA,
    REGISTERED_MCP_STATUS_SCHEMA,
    classify_public_connector_status_failover,
    classify_registered_mcp_connector_status_failover,
)

PHASES = frozenset({"before_unpack", "after_unpack"})
SCHEMA_VERSION = "jazn_chatgpt_ingress_capability/v1"


def negotiate_chatgpt_ingress(
    *,
    phase: str,
    callable_tool_names: object = None,
    current_message_toolset_observed: bool | None = None,
    status_invoked_in_current_message: bool | None = None,
    status_payload: Mapping[str, Any] | None = None,
    local_process_created: bool | None = None,
    system_operator_verified: bool | None = None,
    now_utc: datetime | None = None,
) -> dict[str, Any]:
    """Choose one *candidate* execution route without inferring finalization.

    Remote readiness requires four tools exposed on this message and a fresh
    status actually invoked from that same surface. Local process creation is
    only a bootstrap capability, never live SYSTEM or accepted-turn evidence.
    MEMORY cannot influence either transport decision.
    """

    if phase not in PHASES:
        raise ValueError("unsupported_chatgpt_ingress_phase")

    toolset = classify_current_message_toolset(
        callable_tool_names,
        current_message_toolset_observed=current_message_toolset_observed,
    )
    status = status_payload if isinstance(status_payload, Mapping) else {}
    status_kind = status.get("evidence_schema")
    remote: dict[str, Any] | None = None
    if status_kind == PUBLIC_CONNECTOR_STATUS_SCHEMA:
        remote = classify_public_connector_status_failover(
            status_payload=status,
            host_connector_invocation_observed=status_invoked_in_current_message,
            callable_tool_names=callable_tool_names,
            current_message_toolset_observed=current_message_toolset_observed,
            now_utc=now_utc,
        )
    elif status_kind == REGISTERED_MCP_STATUS_SCHEMA:
        remote = classify_registered_mcp_connector_status_failover(
            status_payload=status,
            host_connector_invocation_observed=status_invoked_in_current_message,
            callable_tool_names=callable_tool_names,
            current_message_toolset_observed=current_message_toolset_observed,
            now_utc=now_utc,
        )

    remote_ready = bool(
        remote is not None and remote["remote_runtime_transport_available"] is True
    )
    process_confirmed = local_process_created is True
    operator_confirmed = bool(phase == "after_unpack" and system_operator_verified is True)

    if remote_ready:
        route = "remote_runtime"
        next_action = "submit_exactly_one_turn_via_verified_remote_mcp"
    elif process_confirmed and not operator_confirmed:
        route = "local_bootstrap"
        next_action = "discover_verify_and_materialize_system_operator"
    elif process_confirmed and operator_confirmed:
        route = "local_bootstrap"
        next_action = "run_canonical_preflight_start_and_live_status"
    else:
        route = "host_diagnostic"
        next_action = "report_capability_evidence_and_stop_without_impersonation"

    if remote is not None:
        remote_reason = str(remote["reason_code"])
        remote_blockers = list(remote["blocking_checks"])
    elif status:
        remote_reason = "unsupported_status_schema"
        remote_blockers = ["remote_status_contract_not_verified"]
    elif toolset["full_turn_toolset_callable"]:
        remote_reason = "status_not_invoked_or_not_available"
        remote_blockers = ["fresh_jazn_status_invocation_required"]
    else:
        remote_reason = str(toolset["reason_code"])
        remote_blockers = ["full_turn_toolset_callable"]

    return {
        "schema_version": SCHEMA_VERSION,
        "phase": phase,
        "execution_route": route,
        "next_action": next_action,
        "remote_runtime_available": remote_ready,
        "remote_transport": remote["remote_transport"] if remote_ready and remote else None,
        "remote_reason_code": remote_reason,
        "remote_blocking_checks": remote_blockers,
        "required_current_message_tools": toolset["required_chatgpt_turn_tools"],
        "missing_current_message_tools": toolset["missing_required_chatgpt_turn_tools"],
        "current_message_toolset_observed": toolset["current_message_toolset_observed"],
        "full_turn_toolset_callable": toolset["full_turn_toolset_callable"],
        "local_executor_process_created": process_confirmed if local_process_created is not None else None,
        "materialized_operator_verified": operator_confirmed if phase == "after_unpack" else None,
        "local_runtime_ready": False,
        "accepted_visible_turn": False,
        "memory_required_for_core_ingress": False,
        "truth_boundary": (
            "This is a read-only decision over host-supplied observations, not an "
            "independent host attestation. No package, process probe, plugin "
            "listing, URL, or memory file can supply absent ChatGPT tools. "
            "Local readiness needs later live status; visible Jaźń speech still "
            "requires accepted display_exact and finalization."
        ),
    }


def _optional_report_boolean(source: Mapping[str, Any], key: str) -> bool | None:
    value = source.get(key)
    if value is not None and not isinstance(value, bool):
        raise ValueError(f"{key}_must_be_boolean")
    return value


def main(argv: list[str] | None = None) -> int:
    """Read-only operator check for *host-collected* current-message evidence.

    This command cannot independently verify that ChatGPT actually invoked the
    app. It never reads tokens or emits unredacted input/status payloads.
    """
    parser = argparse.ArgumentParser(description="Jaźń ChatGPT pre/post unpack host capability gate")
    parser.add_argument("--phase", choices=sorted(PHASES), required=True)
    parser.add_argument("--evidence-file", required=True, help="JSON object path or '-' for stdin")
    args = parser.parse_args(argv)
    try:
        if args.evidence_file == "-":
            raw = sys.stdin.read(65537)
        else:
            path = Path(args.evidence_file).expanduser()
            if path.stat().st_size > 65536:
                raise ValueError("host_evidence_too_large")
            raw = path.read_text(encoding="utf-8")
        if len(raw.encode("utf-8")) > 65536:
            raise ValueError("host_evidence_too_large")
        evidence = json.loads(raw)
        if not isinstance(evidence, dict):
            raise ValueError("host_evidence_must_be_object")
        status = evidence.get("status_payload")
        if status is not None and not isinstance(status, dict):
            raise ValueError("status_payload_must_be_object")
        report = negotiate_chatgpt_ingress(
            phase=args.phase,
            callable_tool_names=evidence.get("callable_tool_names"),
            current_message_toolset_observed=_optional_report_boolean(
                evidence, "current_message_toolset_observed"
            ),
            status_invoked_in_current_message=_optional_report_boolean(
                evidence, "status_invoked_in_current_message"
            ),
            status_payload=status,
            local_process_created=_optional_report_boolean(evidence, "local_process_created"),
            system_operator_verified=_optional_report_boolean(evidence, "system_operator_verified"),
        )
    except (OSError, UnicodeError, ValueError, TypeError):
        print(json.dumps({"ok": False, "reason_code": "invalid_host_capability_evidence"}))
        return 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if report["execution_route"] != "host_diagnostic" else 2


__all__ = ["PHASES", "SCHEMA_VERSION", "negotiate_chatgpt_ingress", "main"]


if __name__ == "__main__":
    raise SystemExit(main())
