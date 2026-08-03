from __future__ import annotations

from pathlib import Path
from typing import Any

from latka_jazn.config import JaznConfig
from latka_jazn.core.chat_command_contract import command_contract, persist_chatgpt_host_visible_reply
from latka_jazn.core.chatgpt_host_pending_store import (
    HostRequestStoreError,
    resolve_continuation_token,
)
from latka_jazn.core.host_visible_finalization import sha256_host_visible_text


def _error(reason: str, **details: Any) -> dict[str, Any]:
    state = str(details.pop("state", "reject") or "reject")
    structured: dict[str, Any] = {
        "ok": False,
        "accepted": False,
        "action": "host_diagnostic",
        "state": state,
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
) -> dict[str, Any]:
    canonical_hash = sha256_host_visible_text(final_text)
    supplied_hash = str(final_text_sha256 or "").strip().lower()
    if supplied_hash != canonical_hash:
        return _error(
            "final_text_sha256_mismatch",
            supplied_text_sha256=supplied_hash or None,
            calculated_text_sha256=canonical_hash,
        )

    runtime_root = Path(root).expanduser().resolve()
    try:
        pending = resolve_continuation_token(runtime_root, continuation_token)
    except HostRequestStoreError as exc:
        return _error(f"host_request:{exc}")

    binding = pending.get("binding") if isinstance(pending.get("binding"), dict) else {}
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
        return _error("pending_binding_incomplete", missing_fields=missing_binding)

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
        "used_memory_item_ids": list(used_memory_item_ids or [])[:8],
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
        repairable = bool(errors) and all(str(item).startswith("host_candidate_repair:") for item in errors)
        return _error(
            "runtime_finalization_rejected",
            state="repair" if repairable else "reject",
            violations=list(errors),
            turn_id=binding["turn_id"],
            trace_id=binding["trace_id"],
        )

    presentation = persisted.get("chatgpt_host_presentation")
    if not isinstance(presentation, dict):
        from latka_jazn.core.chat_command_contract import build_chatgpt_host_presentation_packet

        presentation = build_chatgpt_host_presentation_packet(persisted)
    final_visible_text = str(
        presentation.get("final_visible_text")
        or persisted.get("final_visible_text")
        or ""
    )
    if str(presentation.get("action") or "") != "display_exact" or not final_visible_text:
        return _error(
            "runtime_did_not_accept_final_visible_text",
            turn_id=binding["turn_id"],
            trace_id=binding["trace_id"],
        )

    final_hash = sha256_host_visible_text(final_visible_text)
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
            "used_memory_item_ids": list(used_memory_item_ids or [])[:8],
            "host_model_candidate_validation": persisted.get("host_model_candidate_validation"),
            "host_visible_finalization": persisted.get("host_visible_finalization"),
            "host_request_consumption": persisted.get("host_request_consumption"),
        },
        "_meta": {
            "transport": "authenticated_private_mcp",
            "continuation_consumed": True,
        },
        "isError": False,
    }
