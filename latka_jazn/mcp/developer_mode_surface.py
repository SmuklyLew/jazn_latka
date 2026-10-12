from __future__ import annotations

"""ChatGPT Developer Mode aliases over the canonical Jaźń MCP turn contract.

This module is intentionally transport-only. It does not own runtime lifecycle,
memory, cognition, host-visible finalization, or durable turn state. Its public
clientTurnId is mapped byte-for-byte to the canonical daemon request_id so
retries and reconnects converge on the already-existing Jaźń idempotency and
resume machinery instead of creating a second turn.
"""

from copy import deepcopy
from typing import Any, Mapping

from latka_jazn.version import PACKAGE_VERSION_FULL

JAZN_TURN_TOOL = "jazn_turn"
JAZN_RESUME_TURN_TOOL = "jazn_resume_turn"
JAZN_HEALTH_TOOL = "jazn_health"
JAZN_MEMORY_STATUS_TOOL = "jazn_memory_status"

CANONICAL_GENERATE_TOOL = "jazn_generate_visible_reply"
CANONICAL_RESUME_TOOL = "jazn_resume_visible_reply"
CANONICAL_STATUS_TOOL = "jazn_status"

DEVELOPER_MODE_ALIAS_TO_CANONICAL = {
    JAZN_TURN_TOOL: CANONICAL_GENERATE_TOOL,
    JAZN_RESUME_TURN_TOOL: CANONICAL_RESUME_TOOL,
    JAZN_HEALTH_TOOL: CANONICAL_STATUS_TOOL,
    JAZN_MEMORY_STATUS_TOOL: CANONICAL_STATUS_TOOL,
}

MODEL_VISIBLE_CANONICAL_TOOL_NAMES = frozenset(
    {
        CANONICAL_GENERATE_TOOL,
        CANONICAL_RESUME_TOOL,
        CANONICAL_STATUS_TOOL,
        "jazn_finalize_reply",
    }
)

# Canonical ChatGPT ingress actions must remain discoverable by the model.
# Only operator/audit internals stay hidden from the modern public surface.
MODERN_INTERNAL_TOOL_NAMES = frozenset({"jazn_audit_lookup"})

DEVELOPER_MODE_TOOL_DEFINITIONS: tuple[dict[str, Any], ...] = (
    {
        "name": JAZN_TURN_TOOL,
        "title": "Send this message to Jaźń",
        "description": (
            "Primary ChatGPT Developer Mode entrypoint for every ordinary user message while the Jaźń app "
            "is selected. clientTurnId is the stable idempotency identity for the turn; retry the same id "
            "after an ambiguous transport outcome and never create a second id for the same user message."
        ),
        "inputSchema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "clientTurnId": {"type": "string", "minLength": 1, "maxLength": 256},
                "message": {"type": "string", "minLength": 1, "maxLength": 262144},
                "sessionId": {"type": "string", "minLength": 1, "maxLength": 128},
            },
            "required": ["clientTurnId", "message"],
        },
        "annotations": {
            "readOnlyHint": False,
            "destructiveHint": False,
            "openWorldHint": False,
            "idempotentHint": True,
        },
        "_meta": {"ui": {"visibility": ["app"]}},
    },
    {
        "name": JAZN_RESUME_TURN_TOOL,
        "title": "Resume the same Jaźń turn",
        "description": (
            "Read or resume the already submitted Jaźń turn identified by clientTurnId. "
            "Never resubmit the original user message when this tool is used."
        ),
        "inputSchema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "clientTurnId": {"type": "string", "minLength": 1, "maxLength": 256},
            },
            "required": ["clientTurnId"],
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "openWorldHint": False,
            "idempotentHint": True,
        },
        "_meta": {"ui": {"visibility": ["app"]}},
    },
    {
        "name": JAZN_HEALTH_TOOL,
        "title": "Read Jaźń gateway health",
        "description": (
            "Read redacted transport liveness. This is diagnostic only and does not start a conversation turn."
        ),
        "inputSchema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {},
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "openWorldHint": False,
            "idempotentHint": True,
        },
        "_meta": {"ui": {"visibility": ["app"]}},
    },
    {
        "name": JAZN_MEMORY_STATUS_TOOL,
        "title": "Read Jaźń memory readiness",
        "description": (
            "Read only redacted persistent-memory and recall readiness. Raw memory content and local paths "
            "are never returned by this diagnostic tool."
        ),
        "inputSchema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {},
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "openWorldHint": False,
            "idempotentHint": True,
        },
        "_meta": {"ui": {"visibility": ["app"]}},
    },
)


def _only(arguments: Mapping[str, Any], allowed: set[str], *, tool_name: str) -> None:
    unexpected = sorted(str(key) for key in arguments if str(key) not in allowed)
    if unexpected:
        raise ValueError(
            f"{tool_name}_unsupported_arguments:" + ",".join(unexpected)
        )


def _client_turn_id(arguments: Mapping[str, Any]) -> str:
    value = arguments.get("clientTurnId")
    if not isinstance(value, str) or not value.strip():
        raise ValueError("clientTurnId_required")
    normalized = value.strip()
    if len(normalized) > 256:
        raise ValueError("clientTurnId_too_large")
    return normalized


def translate_developer_mode_tool_call(
    tool_name: str,
    arguments: Mapping[str, Any] | None,
) -> tuple[str, dict[str, Any], str | None]:
    """Translate public Developer Mode aliases to canonical Jaźń tool calls."""

    name = str(tool_name or "").strip()
    args = dict(arguments or {})
    if name == JAZN_TURN_TOOL:
        _only(args, {"clientTurnId", "message", "sessionId"}, tool_name=name)
        client_turn_id = _client_turn_id(args)
        message = args.get("message")
        if not isinstance(message, str) or not message:
            raise ValueError("message_required")
        if len(message) > 262_144:
            raise ValueError("message_too_large")
        canonical: dict[str, Any] = {
            "request_id": client_turn_id,
            "message": message,
        }
        session_id = args.get("sessionId")
        if session_id is not None:
            if not isinstance(session_id, str) or not session_id.strip():
                raise ValueError("sessionId_must_be_nonempty_string")
            if len(session_id) > 128:
                raise ValueError("sessionId_too_large")
            canonical["session_id"] = session_id
        return CANONICAL_GENERATE_TOOL, canonical, client_turn_id

    if name == JAZN_RESUME_TURN_TOOL:
        _only(args, {"clientTurnId"}, tool_name=name)
        client_turn_id = _client_turn_id(args)
        return (
            CANONICAL_RESUME_TOOL,
            {"daemon_request_id": client_turn_id},
            client_turn_id,
        )

    if name in {JAZN_HEALTH_TOOL, JAZN_MEMORY_STATUS_TOOL}:
        _only(args, set(), tool_name=name)
        return CANONICAL_STATUS_TOOL, {}, None

    return name, args, None


def _tool_result(
    *,
    text: str,
    structured: Mapping[str, Any],
    is_error: bool = False,
    meta: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "content": [{"type": "text", "text": str(text)}],
        "structuredContent": dict(structured),
        "_meta": dict(meta or {}),
        "isError": bool(is_error),
    }


def _memory_readiness(status: Mapping[str, Any]) -> dict[str, Any]:
    capability = status.get("capability_matrix")
    capability_map = dict(capability) if isinstance(capability, Mapping) else {}
    components = capability_map.get("components")
    components_map = dict(components) if isinstance(components, Mapping) else {}
    result: dict[str, Any] = {
        "package_version": PACKAGE_VERSION_FULL,
        "full_autobiographical_recall_ready": (
            capability_map.get("full_autobiographical_recall_ready") is True
        ),
        "continuity_ready": capability_map.get("continuity_ready") is True,
    }
    for name in ("persistent_memory", "recall"):
        value = components_map.get(name)
        item = dict(value) if isinstance(value, Mapping) else {}
        result[name] = {
            "status": item.get("status"),
            "available": item.get("available") is True,
            "required_for_dialogue": item.get("required_for_dialogue") is True,
            "reason": item.get("reason"),
        }
    return result


def adapt_developer_mode_tool_result(
    public_tool_name: str,
    value: Mapping[str, Any],
    *,
    client_turn_id: str | None = None,
    protocol_version: str,
    transport: str,
    gateway_instance_id: str | None = None,
    observed_at_utc: str | None = None,
) -> dict[str, Any]:
    """Redact diagnostic aliases and bind turn aliases back to clientTurnId."""

    name = str(public_tool_name or "").strip()
    copied = deepcopy(dict(value))

    if name in {JAZN_TURN_TOOL, JAZN_RESUME_TURN_TOOL}:
        if not client_turn_id:
            raise ValueError("clientTurnId_required_for_turn_result")
        structured_value = copied.get("structuredContent")
        structured = (
            dict(structured_value) if isinstance(structured_value, Mapping) else {}
        )
        structured["clientTurnId"] = client_turn_id
        if str(structured.get("action") or "") == "poll_runtime":
            structured["resume_tool"] = JAZN_RESUME_TURN_TOOL
            structured["poll_command"] = JAZN_RESUME_TURN_TOOL
            structured["must_not_resubmit_user_message"] = True
        copied["structuredContent"] = structured
        meta_value = copied.get("_meta")
        meta = dict(meta_value) if isinstance(meta_value, Mapping) else {}
        meta["developer_mode_turn"] = {
            "clientTurnId": client_turn_id,
            "canonical_request_id": client_turn_id,
            "resume_tool": JAZN_RESUME_TURN_TOOL,
        }
        copied["_meta"] = meta
        return copied

    structured_value = copied.get("structuredContent")
    private_status = (
        dict(structured_value) if isinstance(structured_value, Mapping) else {}
    )
    if name == JAZN_HEALTH_TOOL:
        gateway_live = private_status.get("gateway_ok") is True
        structured: dict[str, Any] = {
            "ok": gateway_live,
            "gateway_live": gateway_live,
            "daemon_reachable": private_status.get("daemon_reachable") is True,
            "protocol_version": protocol_version,
            "package_version": PACKAGE_VERSION_FULL,
            "transport": transport,
        }
        if gateway_instance_id:
            structured["gateway_instance_id"] = gateway_instance_id
        if observed_at_utc:
            structured["observed_at_utc"] = observed_at_utc
        return _tool_result(
            text=(
                "Jaźń MCP gateway is live."
                if gateway_live
                else "Jaźń MCP gateway health is unavailable."
            ),
            structured=structured,
            is_error=not gateway_live,
        )

    if name == JAZN_MEMORY_STATUS_TOOL:
        structured = _memory_readiness(private_status)
        structured.update(
            {
                "ok": True,
                "protocol_version": protocol_version,
                "transport": transport,
            }
        )
        if gateway_instance_id:
            structured["gateway_instance_id"] = gateway_instance_id
        if observed_at_utc:
            structured["observed_at_utc"] = observed_at_utc
        return _tool_result(
            text="Jaźń memory readiness was read without returning memory content.",
            structured=structured,
            is_error=False,
        )

    return copied


__all__ = [
    "CANONICAL_GENERATE_TOOL",
    "CANONICAL_RESUME_TOOL",
    "CANONICAL_STATUS_TOOL",
    "DEVELOPER_MODE_ALIAS_TO_CANONICAL",
    "DEVELOPER_MODE_TOOL_DEFINITIONS",
    "JAZN_HEALTH_TOOL",
    "JAZN_MEMORY_STATUS_TOOL",
    "JAZN_RESUME_TURN_TOOL",
    "JAZN_TURN_TOOL",
    "MODEL_VISIBLE_CANONICAL_TOOL_NAMES",
    "MODERN_INTERNAL_TOOL_NAMES",
    "adapt_developer_mode_tool_result",
    "translate_developer_mode_tool_call",
]
