from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("mcp")
from mcp import Client

from latka_jazn.mcp.http_gateway import build_public_mcp_gateway
from latka_jazn.version import PACKAGE_VERSION_FULL


class _StatusBackend:
    def call_tool(self, name: str, arguments: dict[str, Any], *, meta: dict[str, Any] | None = None) -> dict[str, Any]:
        assert name == "jazn_status"
        return {
            "structuredContent": {
                "ok": True,
                "daemon_reachable": True,
                "daemon": {
                    "daemon_instance_id": "gateway-nonce-daemon",
                    "runtime_version": PACKAGE_VERSION_FULL,
                    "last_heartbeat_at_utc": datetime.now(timezone.utc).isoformat(),
                },
                "capability_matrix": {"conversation_ready": True},
            },
        }


@pytest.mark.anyio
async def test_status_nonce_echo_requires_actual_tool_call(tmp_path: Path) -> None:
    gateway = build_public_mcp_gateway(
        root=tmp_path, backend=_StatusBackend(),
        allow_unauthenticated_loopback_dev=True,
    )
    nonce_a = "0123456789abcdef0123456789abcdef"
    nonce_b = "abcdef0123456789abcdef0123456789"

    async with Client(gateway.mcp, raise_exceptions=True) as client:
        listing = await client.list_tools()
        status_tool = next(t for t in listing.tools if t.name == "jazn_status")
        assert "probe_nonce" in status_tool.input_schema["properties"]

        first = await client.call_tool("jazn_status", {"probe_nonce": nonce_a})
        second = await client.call_tool("jazn_status", {"probe_nonce": nonce_b})
        ordinary = await client.call_tool("jazn_status", {})

    assert first.is_error is False
    assert second.is_error is False
    assert first.structured_content is not None
    assert second.structured_content is not None
    assert ordinary.structured_content is not None
    assert first.structured_content["challenge_nonce_echo"] == nonce_a
    assert second.structured_content["challenge_nonce_echo"] == nonce_b
    assert ordinary.structured_content["challenge_nonce_echo"] is None
    for result in (first, second, ordinary):
        assert result.structured_content is not None
        assert result.structured_content["host_message_toolset_verified"] is False
        assert result.structured_content["accepted_visible_turn_verified"] is False
