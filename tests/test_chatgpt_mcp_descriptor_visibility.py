from __future__ import annotations

"""Contract tests for real FastMCP descriptors, not synthetic catalog fixtures."""

from pathlib import Path
from typing import Any, cast

import pytest

pytest.importorskip("mcp")
from mcp.server.auth.provider import TokenVerifier

from latka_jazn.mcp.chatgpt_toolset import REQUIRED_CHATGPT_TURN_TOOLS
from latka_jazn.mcp.http_gateway import (
    SCOPE_CONNECT,
    SCOPE_STATUS_READ,
    SCOPE_TURN_FINALIZE,
    SCOPE_TURN_READ,
    SCOPE_TURN_SUBMIT,
    build_public_mcp_gateway,
)


class _NoBackendCalls:
    def call_tool(
        self, name: str, arguments: dict[str, Any],
        *, meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        raise AssertionError("MCP catalog inspection must be read-only")


@pytest.mark.anyio
@pytest.mark.parametrize("public_oauth", [False, True])
async def test_official_fastmcp_descriptor_visibility_and_scopes(
    tmp_path: Path, public_oauth: bool,
) -> None:
    options: dict[str, Any] = {
        "root": tmp_path,
        "backend": _NoBackendCalls(),
    }
    if public_oauth:
        options.update({
            "token_verifier": cast(TokenVerifier, object()),
            "oauth_issuer_url": "https://id.example.test",
            "oauth_resource_server_url": "https://jazn.example.test/mcp",
        })
    else:
        options["allow_unauthenticated_loopback_dev"] = True

    gateway = build_public_mcp_gateway(**options)
    descriptors = {
        tool.name: tool.model_dump(by_alias=True, exclude_none=True)
        for tool in await gateway.mcp.list_tools()
    }
    assert set(descriptors) == {
        *REQUIRED_CHATGPT_TURN_TOOLS,
        "jazn_health",
        "jazn_memory_status",
    }

    scopes = {
        "jazn_status": SCOPE_STATUS_READ,
        "jazn_generate_visible_reply": SCOPE_TURN_SUBMIT,
        "jazn_resume_visible_reply": SCOPE_TURN_READ,
        "jazn_finalize_reply": SCOPE_TURN_FINALIZE,
        "jazn_health": SCOPE_STATUS_READ,
        "jazn_memory_status": SCOPE_STATUS_READ,
    }
    for name, descriptor in descriptors.items():
        expected_visibility = (
            ["model", "app"] if name in REQUIRED_CHATGPT_TURN_TOOLS
            else ["app"]
        )
        assert descriptor["_meta"]["ui"]["visibility"] == expected_visibility
        if public_oauth:
            assert descriptor["_meta"]["securitySchemes"] == [
                {"type": "oauth2", "scopes": [SCOPE_CONNECT, scopes[name]]},
            ]
        else:
            assert descriptor["_meta"]["securitySchemes"] == [{"type": "noauth"}]
        annotations = descriptor["annotations"]
        assert annotations["readOnlyHint"] is (
            name not in {"jazn_generate_visible_reply", "jazn_finalize_reply"}
        )
        assert annotations["destructiveHint"] is False
        assert annotations["openWorldHint"] is False
        assert annotations["idempotentHint"] is True
