from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from latka_jazn.bridge.secure_host_runtime_gateway import GatewayConfig, GatewayError, SecureHostRuntimeGateway
from latka_jazn.config import JaznConfig
from latka_jazn.core.chat_command_contract import (
    build_chatgpt_host_presentation_packet,
    chat_gpt_contract,
    persist_chatgpt_host_visible_reply,
)
from latka_jazn.core.chatgpt_host_pending_store import (
    HostRequestStoreError,
    host_request_lifecycle_state,
    mark_daemon_finalization_notification,
)
from latka_jazn.core.host_action_evidence import host_action_evidence_scope


MAX_EXTERNAL_TOOL_EVIDENCE = 8
MAX_HOST_ACTION_EVIDENCE = 8
MAX_USED_MEMORY_ITEM_IDS = 8


def _read_external_tool_evidence(path: Path | None) -> list[dict[str, Any]]:
    if path is None:
        return []
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, list):
        raise ValueError("external_tool_evidence_must_be_json_array")
    if len(value) > MAX_EXTERNAL_TOOL_EVIDENCE:
        raise ValueError("external_tool_evidence_limit_exceeded")
    result: list[dict[str, Any]] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise ValueError(f"external_tool_evidence_not_object:{index}")
        result.append(dict(item))
    return result




def _read_host_action_evidence(path: Path | None) -> list[dict[str, Any]]:
    if path is None:
        return []
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, list):
        raise ValueError("host_action_evidence_must_be_json_array")
    if len(value) > MAX_HOST_ACTION_EVIDENCE:
        raise ValueError("host_action_evidence_limit_exceeded")
    result: list[dict[str, Any]] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise ValueError(f"host_action_evidence_not_object:{index}")
        result.append(dict(item))
    return result

def _lifecycle_record(root: Path, turn_id: str) -> dict[str, Any]:
    state = host_request_lifecycle_state(root, turn_id=turn_id)
    return {
        "request_contract_hash": state.get("request_contract_hash"),
        "binding": dict(state.get("binding") or {}),
        "generation_context": {},
    }


def _notify_daemon(
    *,
    root: Path,
    daemon_host: str,
    daemon_port: int,
    turn_id: str,
    outcome: str,
    reason: str,
    terminal: bool,
) -> dict[str, Any]:
    try:
        record = _lifecycle_record(root, turn_id)
        binding = dict(record.get("binding") or {})
        if not str(binding.get("daemon_request_id") or "").strip():
            return {"ok": True, "not_applicable": True, "reason": "one_shot_without_daemon_job"}
        gateway = SecureHostRuntimeGateway(
            GatewayConfig(
                daemon_url=f"http://{daemon_host}:{int(daemon_port)}",
                runtime_root=root,
            )
        )
        return gateway.note_host_finalization(
            record,
            outcome=outcome,
            reason=reason,
            terminal=terminal,
        )
    except (GatewayError, OSError, ValueError, TypeError) as exc:
        # Durable request consumption is authoritative.  A lost daemon ACK is
        # recoverable because runtime_daemon reconciles the consumed request
        # state before admitting a successor turn.
        return {
            "ok": False,
            "error_code": "daemon_host_finalization_notification_failed",
            "error": f"{type(exc).__name__}:{exc}",
            "recoverable_by_durable_reconciliation": True,
        }


def finalize_payload(args: Any) -> dict[str, Any]:
    """Complete the canonical phase-2 host-visible finalization lifecycle.

    Unlike the pre-v16.3.25.5.41 implementation this function does not stop at
    envelope/hash validation.  It binds phase 2 to one pending phase-1 request,
    persists the accepted visible reply, consumes the request exactly once and
    then acknowledges the daemon lifecycle.  The consumed store remains the
    recovery authority if the daemon ACK is lost.
    """
    root = Path(args.root).expanduser().resolve()
    host_request_contract_hash = str(getattr(args, "host_request_contract_hash", "") or "").strip().lower()
    if not host_request_contract_hash:
        return {
            "ok": False,
            "accepted": False,
            "error_code": "host_request_contract_hash_required",
            "truth_boundary": "Canonical phase-2 finalization requires the persisted phase-1 request binding.",
        }
    text = str(args.text or "")
    if args.text_file:
        text = args.text_file.read_text(encoding="utf-8-sig")
    used_memory_item_ids = [str(item).strip() for item in (getattr(args, "used_memory_item_id", None) or []) if str(item).strip()]
    if len(used_memory_item_ids) > MAX_USED_MEMORY_ITEM_IDS:
        return {"ok": False, "accepted": False, "error_code": "used_memory_item_ids_limit_exceeded"}
    try:
        external_tool_evidence = _read_external_tool_evidence(getattr(args, "external_tool_evidence_file", None))
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        return {
            "ok": False,
            "accepted": False,
            "error_code": "external_tool_evidence_invalid",
            "error": f"{type(exc).__name__}:{exc}",
        }
    try:
        host_action_evidence = _read_host_action_evidence(getattr(args, "host_action_evidence_file", None))
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        return {
            "ok": False,
            "accepted": False,
            "error_code": "host_action_evidence_invalid",
            "error": f"{type(exc).__name__}:{exc}",
        }

    payload = {
        "type": "host_visible_reply",
        "turn_id": str(args.turn_id),
        "trace_id": str(args.trace_id),
        "host_request_contract_hash": host_request_contract_hash,
        "timestamp_header": str(args.timestamp_header),
        "timezone": str(args.timezone),
        "timestamp_sample_iso": str(args.timestamp_sample_iso),
        "timestamp_source": str(args.timestamp_source),
        "timestamp_trusted": bool(args.timestamp_trusted),
        "author_id": str(args.author_id),
        "author_label": str(args.author_label),
        "author_source": str(args.author_source),
        "state_emoticon": str(args.state_emoticon),
        "final_text": text,
        "final_text_sha256": str(args.text_sha256).strip().lower(),
        "used_memory_item_ids": used_memory_item_ids,
        "external_tool_evidence": external_tool_evidence,
    }
    try:
        with host_action_evidence_scope(
            host_action_evidence,
            expected_turn_id=str(args.turn_id),
            expected_trace_id=str(args.trace_id),
            expected_request_contract_hash=host_request_contract_hash,
        ):
            persisted, errors = persist_chatgpt_host_visible_reply(
                config=JaznConfig(root=root),
                payload=payload,
                chat_bridge_meta={
                    "client": "canonical_host_finalize_cli",
                    "lifecycle": "run_py_host_finalize_phase2",
                    "mode": "two_phase_host_visible_reply",
                    "transport": "local_canonical_cli",
                },
                contract=chat_gpt_contract(process_lifecycle="canonical_cli_two_phase").to_dict(),
            )
    except ValueError as exc:
        return {
            "ok": False,
            "accepted": False,
            "error_code": "host_action_evidence_invalid",
            "error": f"{type(exc).__name__}:{exc}",
        }
    if errors or not isinstance(persisted, dict):
        lifecycle = host_request_lifecycle_state(root, turn_id=str(args.turn_id))
        state = str(lifecycle.get("state") or "")
        outcome = "expired" if state == "expired" else "rejected"
        if state == "indeterminate":
            # The append outcome is genuinely uncertain.  Do not manufacture a
            # second terminal ACK from host-side reconstruction: the durable
            # pending store is the recovery authority and the daemon already
            # reconciles ``indeterminate`` fail-closed.  This avoids turning one
            # uncertainty into a misleading binding-mismatch side failure.
            notification = {
                "ok": True,
                "deferred_to_durable_reconciliation": True,
                "reason": "host_request_persistence_indeterminate",
                "host_request_state": "indeterminate",
            }
        else:
            notification = _notify_daemon(
                root=root,
                daemon_host=str(getattr(args, "daemon_host", "127.0.0.1")),
                daemon_port=int(getattr(args, "daemon_port", 8787)),
                turn_id=str(args.turn_id),
                outcome=outcome,
                reason=";".join(str(item) for item in errors) or "runtime_finalization_rejected",
                terminal=state == "expired",
            )
        return {
            "ok": False,
            "accepted": False,
            "error_code": "runtime_finalization_rejected",
            "violations": [str(item) for item in errors],
            "host_request_lifecycle": lifecycle,
            "daemon_job_lifecycle": notification,
        }

    presentation = persisted.get("chatgpt_host_presentation")
    if not isinstance(presentation, dict):
        presentation = build_chatgpt_host_presentation_packet(persisted)
        persisted["chatgpt_host_presentation"] = presentation
    action = str(presentation.get("action") or "host_diagnostic")
    if action == "generate_then_finalize":
        notification = _notify_daemon(
            root=root,
            daemon_host=str(getattr(args, "daemon_host", "127.0.0.1")),
            daemon_port=int(getattr(args, "daemon_port", 8787)),
            turn_id=str(args.turn_id),
            outcome="regeneration_requested",
            reason="host_candidate_regeneration_requested",
            terminal=False,
        )
        persisted["accepted"] = False
        persisted["daemon_job_lifecycle"] = notification
        return persisted

    final_text = str(presentation.get("final_visible_text") or persisted.get("final_visible_text") or "")
    accepted = action == "display_exact" and bool(final_text)
    notification = _notify_daemon(
        root=root,
        daemon_host=str(getattr(args, "daemon_host", "127.0.0.1")),
        daemon_port=int(getattr(args, "daemon_port", 8787)),
        turn_id=str(args.turn_id),
        outcome="accepted" if accepted else "rejected",
        reason="host_visible_reply_finalized" if accepted else "runtime_did_not_accept_final_visible_text",
        terminal=True,
    )
    persisted["accepted"] = accepted
    persisted["daemon_job_lifecycle"] = notification
    persisted["host_finalization_lifecycle_complete"] = accepted
    if accepted:
        delivered = notification.get("ok") is True
        try:
            persisted["turn_settlement"] = mark_daemon_finalization_notification(
                root,
                turn_id=str(args.turn_id),
                request_contract_hash=host_request_contract_hash,
                delivered=delivered,
                error=(
                    None
                    if delivered
                    else str(
                        notification.get("error_code")
                        or notification.get("error")
                        or "daemon_finalization_notification_failed"
                    )
                ),
            )
        except HostRequestStoreError as exc:
            persisted["turn_settlement_notification_recording"] = {
                "ok": False,
                "error": str(exc),
            }
        if not delivered:
            persisted["host_finalization_lifecycle_complete"] = False
            persisted["host_finalization_recovery_required"] = True
    return persisted



def build_host_finalize_parser(*, default_root: Path) -> argparse.ArgumentParser:
    """Build the canonical ``run.py host-finalize`` parser.

    This command deliberately lives next to the lifecycle implementation rather
    than expanding the legacy aggregate CLI parser.  ``run.py`` intercepts this
    canonical command before compatibility dispatch.
    """
    parser = argparse.ArgumentParser(prog="run.py host-finalize", allow_abbrev=False)
    parser.add_argument("--root", type=Path, default=default_root)
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument("--timestamp-header", required=True)
    parser.add_argument("--timezone", required=True)
    parser.add_argument("--timestamp-sample-iso", required=True)
    parser.add_argument("--timestamp-source", required=True)
    parser.add_argument("--timestamp-trusted", action=argparse.BooleanOptionalAction, required=True)
    parser.add_argument("--author-id", required=True)
    parser.add_argument("--author-label", required=True)
    parser.add_argument("--author-source", required=True)
    parser.add_argument("--state-emoticon", required=True)
    parser.add_argument("--turn-id", required=True)
    parser.add_argument("--trace-id", required=True)
    parser.add_argument("--host-request-contract-hash", required=True)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--text", default="")
    source.add_argument("--text-file", type=Path)
    parser.add_argument("--text-sha256", required=True)
    parser.add_argument("--supplied-turn-id")
    parser.add_argument("--supplied-trace-id")
    parser.add_argument("--used-memory-item-id", action="append", default=[])
    parser.add_argument("--external-tool-evidence-file", type=Path)
    parser.add_argument("--host-action-evidence-file", type=Path)
    parser.add_argument("--daemon-host", default="127.0.0.1")
    parser.add_argument("--daemon-port", type=int, default=8787)
    parser.add_argument("--max-bytes", type=int, default=2 * 1024 * 1024)
    return parser


def run_host_finalize_cli(argv: list[str], *, default_root: Path) -> int:
    args = build_host_finalize_parser(default_root=Path(default_root).resolve()).parse_args(argv)
    payload = finalize_payload(args)
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0 if payload.get("accepted") else 2
