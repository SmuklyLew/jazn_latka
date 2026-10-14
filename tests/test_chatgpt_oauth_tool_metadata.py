from __future__ import annotations

from pathlib import Path
from typing import Any, cast
import pytest

pytest.importorskip("mcp")
from mcp.server.auth.provider import TokenVerifier
from latka_jazn.mcp.http_gateway import (
    SCOPE_CONNECT, SCOPE_STATUS_READ, SCOPE_TURN_SUBMIT,
    SCOPE_TURN_READ, SCOPE_TURN_FINALIZE, build_public_mcp_gateway,
)


class _NoBackendCalls:
    def call_tool(self, name: str, arguments: dict[str, Any],
                  *, meta: dict[str, Any] | None = None) -> dict[str, Any]:
        raise AssertionError("catalog inspection must not execute a tool")


@pytest.mark.anyio
async def test_explicit_local_development_advertises_noauth(tmp_path: Path) -> None:
    server = build_public_mcp_gateway(
        root=tmp_path, backend=_NoBackendCalls(),
        allow_unauthenticated_loopback_dev=True,
    )
    tools = await server.mcp.list_tools()
    assert len(tools) == 6
    for tool in tools:
        wire = tool.model_dump(by_alias=True, exclude_none=True)
        assert wire["_meta"]["securitySchemes"] == [{"type": "noauth"}]


@pytest.mark.anyio
async def test_authenticated_gateway_describes_actual_operation_scopes(tmp_path: Path) -> None:
    server = build_public_mcp_gateway(
        root=tmp_path, backend=_NoBackendCalls(),
        token_verifier=cast(TokenVerifier, object()),
        oauth_issuer_url="https://id.example.test",
        oauth_resource_server_url="https://jazn.example.test/mcp",
    )
    expected = {
        "jazn_status": SCOPE_STATUS_READ,
        "jazn_generate_visible_reply": SCOPE_TURN_SUBMIT,
        "jazn_resume_visible_reply": SCOPE_TURN_READ,
        "jazn_finalize_reply": SCOPE_TURN_FINALIZE,
        "jazn_health": SCOPE_STATUS_READ,
        "jazn_memory_status": SCOPE_STATUS_READ,
    }
    tools = {t.name: t for t in await server.mcp.list_tools()}
    assert set(tools) == set(expected)
    for name, scope in expected.items():
        wire = tools[name].model_dump(by_alias=True, exclude_none=True)
        assert wire["_meta"]["securitySchemes"] == [
            {"type": "oauth2", "scopes": [SCOPE_CONNECT, scope]},
        ]
