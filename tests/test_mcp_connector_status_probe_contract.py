from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("mcp")

from mcp import Client

from latka_jazn.mcp.http_gateway import build_public_mcp_gateway
from latka_jazn.mcp.remote_runtime import (
    EXPECTED_PUBLIC_MCP_PROTOCOL_VERSION,
    PUBLIC_CONNECTOR_STATUS_SCHEMA,
)
from latka_jazn.version import PACKAGE_VERSION_FULL


class _StatusBackend:
    def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
        *,
        meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if name != "jazn_status":
            raise AssertionError(f"unexpected tool: {name}")
        return {
            "content": [{"type": "text", "text": "ready"}],
            "structuredContent": {
                "gateway_ok": True,
                "daemon_reachable": True,
                "daemon": {
                    "daemon_instance_id": "daemon-status-contract-a",
                    "runtime_version": PACKAGE_VERSION_FULL,
                    "last_heartbeat_at_utc": datetime.now(timezone.utc).isoformat(),
                },
                "capability_matrix": {"conversation_ready": True},
            },
            "isError": False,
        }


@pytest.mark.anyio
async def test_jazn_status_emits_self_describing_connector_probe_contract(
    tmp_path: Path,
) -> None:
    gateway = build_public_mcp_gateway(
        root=tmp_path,
        backend=_StatusBackend(),
        allow_unauthenticated_loopback_dev=True,
    )

    async with Client(gateway.mcp, raise_exceptions=True) as client:
        result = await client.call_tool("jazn_status", {})

    assert result.is_error is False
    assert result.structured_content is not None
    status = result.structured_content
    assert status["evidence_schema"] == PUBLIC_CONNECTOR_STATUS_SCHEMA
    assert status["tool_name"] == "jazn_status"
    assert status["protocol_version"] == EXPECTED_PUBLIC_MCP_PROTOCOL_VERSION
    assert status["public_transport"] == "streamable_http"
    assert status["gateway_live"] is True
    assert status["daemon_reachable"] is True
    assert status["ready"] is True
    assert status["gateway_instance_id"]
    assert status["runtime_instance_id"] == "daemon-status-contract-a"
    assert status["runtime_version"] == PACKAGE_VERSION_FULL
    assert status["runtime_heartbeat_at_utc"]
    assert status["observed_at_utc"]
