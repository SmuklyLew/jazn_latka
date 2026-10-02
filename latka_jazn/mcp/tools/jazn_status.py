from __future__ import annotations

from typing import Any

from latka_jazn.bridge.secure_host_runtime_gateway import SecureHostRuntimeGateway
from latka_jazn.mcp.chatgpt_toolset import REQUIRED_CHATGPT_TURN_TOOLS


def run(gateway: SecureHostRuntimeGateway) -> dict[str, Any]:
    status = dict(gateway.status())
    status.update(
        {
            "required_chatgpt_turn_tools": list(REQUIRED_CHATGPT_TURN_TOOLS),
            "fresh_conversation_reverification_required": True,
            "current_message_toolset_observation_required": True,
            "catalog_or_installed_state_sufficient": False,
        }
    )
    text = "Jaźń runtime gateway is ready." if status.get("gateway_ok") else "Jaźń runtime gateway is unavailable."
    return {
        "content": [{"type": "text", "text": text}],
        "structuredContent": status,
        "_meta": {"tool": "jazn_status", "private_operator_detail": True},
        "isError": not bool(status.get("gateway_ok")),
    }
