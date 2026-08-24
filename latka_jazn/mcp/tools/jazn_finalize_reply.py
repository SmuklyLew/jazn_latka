from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from latka_jazn.config import JaznConfig
from latka_jazn.core.chat_command_contract import command_contract, persist_chatgpt_host_visible_reply
from latka_jazn.core.chatgpt_host_pending_store import (
    HostRequestStoreError,
    issue_continuation_token,
    resolve_continuation_token,
)
from latka_jazn.core.host_visible_finalization import sha256_host_visible_text


class HostFinalizationLifecycleGateway(Protocol):
    def note_host_finalization(
        self,
        pending: dict[str, Any],
        *,
        outcome: str,
        reason: str,
        terminal: bool = False,
    ) -> dict[str, Any]: ...


def _notify_lifecycle(
    gateway: HostFinalizationLifecycleGateway | None,
    pending: dict[str, Any],
    *,
    outcome: str,
    reason: str,
    terminal: bool = False,
) -> dict[str, Any]:
    if gateway is None or not pending:
        return {"ok": True, "not_applicable": True}
    try:
        return gateway.note_host_finalization(
            pending,
            outcome=outcome,
            reason=reason,
            terminal=terminal,
        )
    except Exception as exc:
        return {
            "ok": False,
            "error_code": "daemon_host_finalization_notification_failed",
            "error": f"{type(exc).__name__}:{exc}",
        }


def _error(reason: str, **details: Any) -> dict[str, Any]:
    structured: dict[str, Any] = {
        "ok": False,
        "accepted": False,
        "action": "host_diagnostic",
        "state": "reject",
        "reason": reason,
    }
    structured.update(details)
    return {
        "content": [{"type": "text", "text": f"Host-visible finalization failed safely: {reason}."}],
        "structuredContent": structured,
        "_meta": {},
        "isError": True,
    }


def run(
    *,
    root: Path,
    continuation_token: str,
    final_text: str,
    final_text_sha256: str,
    used_memory_item_ids: list[str] | None = None,
    external_tool_evidence: list[dict[str, Any]] | None = None,
    lifecycle_gateway: HostFinalizationLifecycleGateway | None = None,
) -> dict[str, Any]:
    runtime_root = Path(root).expanduser().resolve()
    try:
        pending = resolve_continuation_token(runtime_root, continuation_token)
    except HostRequestStoreError as exc:
        reason = str(exc)
        outcome = (
            "replay_rejected"
            if reason == "host_request_replay_detected"
            else "expired"
            if reason == "host_request_expired"
            else "rejected"
        )
        lifecycle = _notify_lifecycle(
            lifecycle_gateway,
            dict(getattr(exc, "record", {}) or {}),
            outcome=outcome,
            reason=reason,
            terminal=reason in {"host_request_expired", "host_request_persistence_indeterminate"},
        )
        return _error(f"host_request:{exc}", daemon_job_lifecycle=lifecycle)

    canonical_hash = sha256_host_visible_text(final_text)
    supplied_hash = str(final_text_sha256 or "").strip().lower()
    if supplied_hash != canonical_hash:
        lifecycle = _notify_lifecycle(
            lifecycle_gateway,
            pending,
            outcome="hash_rejected",
            reason="final_text_sha256_mismatch",
        )
        return _error(
            "final_text_sha256_mismatch",
            supplied_text_sha256=supplied_hash or None,
            calculated_text_sha256=canonical_hash,
            daemon_job_lifecycle=lifecycle,
        )

    binding_value = pending.get("binding")
    binding: dict[str, Any] = binding_value if isinstance(binding_value, dict) else {}
    request_contract_hash = str(pending.get("request_contract_hash") or "").strip().lower()
    required = (
        "turn_id",
        "trace_id",
        "timestamp_header",
        "timezone",
        "timestamp_sample_iso",
        "timestamp_source",
        "author_id",
        "author_label",
        "author_source",
        "state_emoticon",
    )
    missing_binding = [name for name in required if not str(binding.get(name) or "").strip()]
    if not isinstance(binding.get("timestamp_trusted"), bool):
        missing_binding.append("timestamp_trusted")
    if len(request_contract_hash) != 64:
        missing_binding.append("request_contract_hash")
    if missing_binding:
        lifecycle = _notify_lifecycle(
            lifecycle_gateway,
            pending,
            outcome="rejected",
            reason="pending_binding_incomplete",
            terminal=True,
        )
        return _error(
            "pending_binding_incomplete",
            missing_fields=missing_binding,
            daemon_job_lifecycle=lifecycle,
        )

    payload = {
        "type": "host_visible_reply",
        "turn_id": str(binding["turn_id"]),
        "trace_id": str(binding["trace_id"]),
        "host_request_contract_hash": request_contract_hash,
        "timestamp_header": str(binding["timestamp_header"]),
        "timezone": str(binding["timezone"]),
        "timestamp_sample_iso": str(binding["timestamp_sample_iso"]),
        "timestamp_source": str(binding["timestamp_source"]),
        "timestamp_trusted": bool(binding["timestamp_trusted"]),
        "author_id": str(binding["author_id"]),
        "author_label": str(binding["author_label"]),
        "author_source": str(binding["author_source"]),
        "state_emoticon": str(binding["state_emoticon"]),
        "final_text": str(final_text),
        "final_text_sha256": supplied_hash,
        "used_memory_item_ids": list(used_memory_item_ids or []),
        "external_tool_evidence": list(external_tool_evidence or []),
    }
    persisted, errors = persist_chatgpt_host_visible_reply(
        config=JaznConfig(root=runtime_root),
        payload=payload,
        chat_bridge_meta={
            "client": "jazn_private_mcp",
            "lifecycle": "mcp_continuation_finalization",
            "mode": "two_phase_host_visible_reply",
            "transport": "authenticated_private_mcp",
        },
        contract=command_contract("--chat-gpt", process_lifecycle="mcp_two_phase"),
    )
    if errors or not isinstance(persisted, dict):
        reasons = [str(item) for item in errors]
        expired = any("expired" in item for item in reasons)
        terminal = expired or any(
            marker in item
            for item in reasons
            for marker in ("persistence_indeterminate", "regeneration_budget_exhausted")
        )
        lifecycle = _notify_lifecycle(
            lifecycle_gateway,
            pending,
            outcome="expired" if expired else "rejected",
            reason=";".join(reasons) or "runtime_finalization_rejected",
            terminal=terminal,
        )
        return _error(
            "runtime_finalization_rejected",
            violations=reasons,
            turn_id=binding["turn_id"],
            trace_id=binding["trace_id"],
            daemon_job_lifecycle=lifecycle,
        )

    presentation = persisted.get("chatgpt_host_presentation")
    if not isinstance(presentation, dict):
        from latka_jazn.core.chat_command_contract import build_chatgpt_host_presentation_packet

        presentation = build_chatgpt_host_presentation_packet(persisted)
    if str(presentation.get('action') or '') == 'generate_then_finalize':
        bridge_value = presentation.get('chatgpt_host_bridge')
        bridge: dict[str, Any] = bridge_value if isinstance(bridge_value, dict) else {}
        retry_continuation = issue_continuation_token(
            runtime_root,
            turn_id=str(binding["turn_id"]),
            request_contract_hash=request_contract_hash,
        )
        lifecycle = _notify_lifecycle(
            lifecycle_gateway,
            pending,
            outcome="regeneration_requested",
            reason="host_candidate_regeneration_requested",
        )
        return {
            'content': [{'type': 'text', 'text': 'Regenerate once from the same runtime contract, then call jazn_finalize_reply again. Do not display this intermediate result.'}],
            'structuredContent': {
                'ok': True, 'accepted': False, 'action': 'generate_then_finalize',
                'state': 'regenerate', 'continuation_token': retry_continuation['continuation_token'],
                'expires_at_utc': retry_continuation.get('expires_at_utc'),
                'turn_id': binding['turn_id'], 'trace_id': binding['trace_id'],
                'host_request_contract_hash': request_contract_hash,
                'regeneration_attempt': bridge.get('regeneration_attempt'),
                'max_regeneration_attempts': bridge.get('max_regeneration_attempts'),
                'host_generation_policy': bridge.get('host_generation_policy') or {},
                'host_generation_rules': list(bridge.get('host_generation_rules') or []),
                'must_not_display_intermediate': True,
                'daemon_job_lifecycle': lifecycle,
            },
            '_meta': {'transport': 'authenticated_private_mcp', 'continuation_consumed': False},
            'isError': False,
        }

    final_visible_text = str(
        presentation.get("final_visible_text")
        or persisted.get("final_visible_text")
        or ""
    )
    if str(presentation.get("action") or "") != "display_exact" or not final_visible_text:
        lifecycle = _notify_lifecycle(
            lifecycle_gateway,
            pending,
            outcome="rejected",
            reason="runtime_did_not_accept_final_visible_text",
            terminal=True,
        )
        return _error(
            "runtime_did_not_accept_final_visible_text",
            turn_id=binding["turn_id"],
            trace_id=binding["trace_id"],
            daemon_job_lifecycle=lifecycle,
        )

    final_hash = sha256_host_visible_text(final_visible_text)
    lifecycle = _notify_lifecycle(
        lifecycle_gateway,
        pending,
        outcome="accepted",
        reason="host_visible_reply_finalized",
        terminal=True,
    )
    return {
        "content": [{"type": "text", "text": final_visible_text}],
        "structuredContent": {
            "ok": True,
            "accepted": True,
            "action": "display_exact",
            "state": "accept",
            "must_display_exactly": True,
            "final_visible_text": final_visible_text,
            "final_text_sha256": final_hash,
            "input_text_sha256": supplied_hash,
            "turn_id": str(binding["turn_id"]),
            "trace_id": str(binding["trace_id"]),
            "host_request_contract_hash": request_contract_hash,
            "host_visible_finalization": persisted.get("host_visible_finalization"),
            "host_request_consumption": persisted.get("host_request_consumption"),
            "daemon_job_lifecycle": lifecycle,
        },
        "_meta": {
            "transport": "authenticated_private_mcp",
            "continuation_consumed": True,
        },
        "isError": False,
    }
