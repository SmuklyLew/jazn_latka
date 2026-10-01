from __future__ import annotations

from copy import deepcopy

import pytest

from latka_jazn.mcp.developer_mode_surface import (
    DEVELOPER_MODE_TOOL_DEFINITIONS,
    JAZN_HEALTH_TOOL,
    JAZN_MEMORY_STATUS_TOOL,
    JAZN_RESUME_TURN_TOOL,
    JAZN_TURN_TOOL,
    adapt_developer_mode_tool_result,
    translate_developer_mode_tool_call,
)
from latka_jazn.mcp.server import JaznMcpServer
from latka_jazn.mcp.server_legacy_v76 import TOOL_DEFINITIONS


def test_modern_tool_list_exposes_developer_mode_surface_not_internal_turn_names() -> None:
    response = {
        "jsonrpc": "2.0",
        "id": 1,
        "result": {"tools": deepcopy(TOOL_DEFINITIONS)},
    }
    stamped = JaznMcpServer._stamp_modern_response(
        {"method": "tools/list"},
        response,
    )
    assert stamped is not None
    names = {item["name"] for item in stamped["result"]["tools"]}
    assert names == {
        JAZN_TURN_TOOL,
        JAZN_RESUME_TURN_TOOL,
        "jazn_finalize_reply",
        "jazn_status",
        JAZN_HEALTH_TOOL,
        JAZN_MEMORY_STATUS_TOOL,
    }
    assert "jazn_generate_visible_reply" not in names
    assert "jazn_resume_visible_reply" not in names
    assert "jazn_audit_lookup" not in names

    aliases = {item["name"]: item for item in DEVELOPER_MODE_TOOL_DEFINITIONS}
    assert aliases[JAZN_TURN_TOOL]["annotations"]["idempotentHint"] is True
    assert aliases[JAZN_RESUME_TURN_TOOL]["annotations"]["readOnlyHint"] is True


def test_client_turn_id_maps_exactly_to_canonical_request_id() -> None:
    name, args, client_turn_id = translate_developer_mode_tool_call(
        JAZN_TURN_TOOL,
        {
            "clientTurnId": "chatgpt-turn-001",
            "message": "Pierwsza wiadomość nowego czatu.",
            "sessionId": "chatgpt-main",
        },
    )
    assert name == "jazn_generate_visible_reply"
    assert client_turn_id == "chatgpt-turn-001"
    assert args == {
        "request_id": "chatgpt-turn-001",
        "message": "Pierwsza wiadomość nowego czatu.",
        "session_id": "chatgpt-main",
    }


def test_resume_alias_never_accepts_user_message_replay() -> None:
    name, args, client_turn_id = translate_developer_mode_tool_call(
        JAZN_RESUME_TURN_TOOL,
        {"clientTurnId": "chatgpt-turn-002"},
    )
    assert name == "jazn_resume_visible_reply"
    assert args == {"daemon_request_id": "chatgpt-turn-002"}
    assert client_turn_id == "chatgpt-turn-002"

    with pytest.raises(ValueError, match="unsupported_arguments"):
        translate_developer_mode_tool_call(
            JAZN_RESUME_TURN_TOOL,
            {
                "clientTurnId": "chatgpt-turn-002",
                "message": "do not replay",
            },
        )


def test_poll_result_points_back_to_public_resume_alias() -> None:
    value = {
        "content": [{"type": "text", "text": "pending"}],
        "structuredContent": {
            "ok": True,
            "action": "poll_runtime",
            "daemon_request_id": "chatgpt-turn-003",
            "poll_command": "jazn_resume_visible_reply",
        },
        "_meta": {},
        "isError": False,
    }
    adapted = adapt_developer_mode_tool_result(
        JAZN_TURN_TOOL,
        value,
        client_turn_id="chatgpt-turn-003",
        protocol_version="2026-07-28",
        transport="secure_mcp_tunnel_stdio",
    )
    structured = adapted["structuredContent"]
    assert structured["clientTurnId"] == "chatgpt-turn-003"
    assert structured["resume_tool"] == JAZN_RESUME_TURN_TOOL
    assert structured["poll_command"] == JAZN_RESUME_TURN_TOOL
    assert structured["must_not_resubmit_user_message"] is True


def test_memory_status_never_leaks_private_operator_paths() -> None:
    private = {
        "content": [{"type": "text", "text": "private"}],
        "structuredContent": {
            "gateway_ok": True,
            "runtime_root": "D:/PRIVATE/JAZN",
            "daemon": {"pid": 999},
            "capability_matrix": {
                "full_autobiographical_recall_ready": True,
                "continuity_ready": True,
                "components": {
                    "persistent_memory": {
                        "status": "ready",
                        "available": True,
                        "required_for_dialogue": False,
                        "reason": "verified",
                    },
                    "recall": {
                        "status": "ready",
                        "available": True,
                        "required_for_dialogue": False,
                        "reason": "verified",
                    },
                },
            },
        },
        "_meta": {"private_operator_detail": True},
        "isError": False,
    }
    public = adapt_developer_mode_tool_result(
        JAZN_MEMORY_STATUS_TOOL,
        private,
        protocol_version="2026-07-28",
        transport="streamable_http",
    )
    structured = public["structuredContent"]
    assert structured["persistent_memory"]["available"] is True
    assert structured["recall"]["available"] is True
    assert structured["full_autobiographical_recall_ready"] is True
    assert "runtime_root" not in structured
    assert "daemon" not in structured
