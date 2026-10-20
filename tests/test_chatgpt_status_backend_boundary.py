"""A ready daemon must not assert ChatGPT host turn readiness."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("mcp")
from mcp import Client
from mcp.types import TextContent

from latka_jazn.mcp.http_gateway import build_public_mcp_gateway
from latka_jazn.version import PACKAGE_VERSION_FULL


class _ReadyBackend:
    def call_tool(self, name: str, arguments: dict[str, Any], *, meta: dict[str, Any] | None = None) -> dict[str, Any]:
        assert name == "jazn_status"
        return {
            "structuredContent": {
                "ok": True,
                "ready": True,
                "gateway_live": True,
                "daemon_reachable": True,
                "daemon": {
                    "daemon_instance_id": "demo-ready-daemon",
                    "runtime_version": PACKAGE_VERSION_FULL,
                    "last_heartbeat_at_utc": datetime.now(timezone.utc).isoformat(),
                },
                "capability_matrix": {"conversation_ready": True},
            }
        }


@pytest.mark.anyio
async def test_backend_ready_status_cannot_promote_current_chatgpt_message(tmp_path: Path) -> None:
    gateway = build_public_mcp_gateway(root=tmp_path, backend=_ReadyBackend(), allow_unauthenticated_loopback_dev=True)
    async with Client(gateway.mcp, raise_exceptions=True) as client:
        result = await client.call_tool("jazn_status", {})
    assert result.is_error is False
    assert result.structured_content is not None
    s = result.structured_content
    assert s["ready"] is True
    assert s["readiness_scope"] == "backend_only_not_current_chatgpt_turn"
    assert s["host_message_toolset_verified"] is False
    assert s["conversation_wide_auto_routing_verified"] is False
    assert s["accepted_visible_turn_verified"] is False
    assert any(
        "current ChatGPT message routing is unverified" in item.text
        for item in result.content
        if isinstance(item, TextContent)
    )
