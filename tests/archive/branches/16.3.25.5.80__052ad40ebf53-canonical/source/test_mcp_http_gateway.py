from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("mcp")

from mcp import Client

from latka_jazn.mcp.http_gateway import (
    HEALTH_PATH,
    MCP_PATH,
    READINESS_PATH,
    PublicMcpGatewayConfig,
    build_public_mcp_gateway,
)


class _FakeBackend:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any], dict[str, Any]]] = []

    def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
        *,
        meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        metadata = dict(meta or {})
        self.calls.append((name, dict(arguments), metadata))
        if name == "jazn_status":
            return {
                "content": [{"type": "text", "text": "private operator status"}],
                "structuredContent": {
                    "gateway_ok": True,
                    "daemon_reachable": True,
                    "runtime_root": "PRIVATE/ROOT/MUST/NOT/LEAK",
                    "daemon": {"pid": 12345},
                    "capability_matrix": {"conversation_ready": True},
                },
                "_meta": {"private_operator_detail": True},
                "isError": False,
            }
        if name == "jazn_generate_visible_reply":
            request_id = str(arguments["request_id"])
            return {
                "content": [{"type": "text", "text": "pending"}],
                "structuredContent": {
                    "ok": True,
                    "action": "poll_runtime",
                    "request_id": request_id,
                    "daemon_request_id": request_id,
                    "must_not_resubmit_user_message": True,
                },
                "_meta": {"runtime": "test"},
                "isError": False,
            }
        if name == "jazn_resume_visible_reply":
            request_id = str(arguments["daemon_request_id"])
            return {
                "content": [{"type": "text", "text": "still pending"}],
                "structuredContent": {
                    "ok": True,
                    "action": "poll_runtime",
                    "request_id": request_id,
                    "daemon_request_id": request_id,
                    "must_not_resubmit_user_message": True,
                },
                "_meta": {},
                "isError": False,
            }
        if name == "jazn_finalize_reply":
            return {
                "content": [{"type": "text", "text": str(arguments["final_visible_text"])}],
                "structuredContent": {
                    "ok": True,
                    "action": "display_exact",
                    "final_visible_text": str(arguments["final_visible_text"]),
                    "must_display_exactly": True,
                },
                "_meta": {},
                "isError": False,
            }
        raise AssertionError(f"unexpected tool: {name}")


def _gateway(tmp_path: Path, backend: _FakeBackend):
    return build_public_mcp_gateway(
        root=tmp_path,
        backend=backend,
        allow_unauthenticated_loopback_dev=True,
    )


def test_public_gateway_fails_closed_without_oauth_outside_explicit_loopback_dev(tmp_path: Path) -> None:
    backend = _FakeBackend()
    with pytest.raises(ValueError, match="oauth_token_verifier_required"):
        build_public_mcp_gateway(root=tmp_path, backend=backend)

    with pytest.raises(ValueError, match="oauth_token_verifier_required"):
        build_public_mcp_gateway(
            root=tmp_path,
            host="0.0.0.0",
            backend=backend,
            allow_unauthenticated_loopback_dev=True,
            allowed_hosts=("mcp.example.test",),
        )


def test_public_gateway_never_allows_non_loopback_daemon_target(tmp_path: Path) -> None:
    config = PublicMcpGatewayConfig(
        root=tmp_path,
        daemon_url="https://daemon.example.test",
        allow_unauthenticated_loopback_dev=True,
    )
    with pytest.raises(ValueError, match="daemon_must_remain_loopback"):
        config.validate(token_verifier_configured=False)


@pytest.mark.anyio
async def test_official_sdk_exposes_only_minimal_public_tool_surface(tmp_path: Path) -> None:
    backend = _FakeBackend()
    gateway = _gateway(tmp_path, backend)
    async with Client(gateway.mcp, raise_exceptions=True) as client:
        listing = await client.list_tools()

    tools = {tool.name: tool for tool in listing.tools}
    assert set(tools) == {
        "jazn_generate_visible_reply",
        "jazn_resume_visible_reply",
        "jazn_finalize_reply",
        "jazn_status",
    }
    assert "jazn_audit_lookup" not in tools
    generate_schema = tools["jazn_generate_visible_reply"].input_schema
    assert set(generate_schema.get("required", [])) >= {"request_id", "message"}
    assert tools["jazn_generate_visible_reply"].annotations is not None
    assert tools["jazn_generate_visible_reply"].annotations.idempotent_hint is True
    assert tools["jazn_status"].annotations is not None
    assert tools["jazn_status"].annotations.read_only_hint is True


@pytest.mark.anyio
async def test_generate_forwards_stable_request_id_through_private_backend_token(tmp_path: Path) -> None:
    backend = _FakeBackend()
    gateway = _gateway(tmp_path, backend)
    async with Client(gateway.mcp, raise_exceptions=True) as client:
        result = await client.call_tool(
            "jazn_generate_visible_reply",
            {"request_id": "req-v78-1", "message": "hello", "session_id": "chatgpt-main"},
        )

    assert result.is_error is False
    assert result.structured_content is not None
    assert result.structured_content["action"] == "poll_runtime"
    assert result.structured_content["daemon_request_id"] == "req-v78-1"
    assert backend.calls[-1][0] == "jazn_generate_visible_reply"
    assert backend.calls[-1][1]["request_id"] == "req-v78-1"
    assert backend.calls[-1][2]["authorization"]
    assert backend.calls[-1][2]["subject"] == "loopback-development"


@pytest.mark.anyio
async def test_public_status_is_redacted_even_when_backend_status_is_private(tmp_path: Path) -> None:
    backend = _FakeBackend()
    gateway = _gateway(tmp_path, backend)
    async with Client(gateway.mcp, raise_exceptions=True) as client:
        result = await client.call_tool("jazn_status", {})

    assert result.is_error is False
    assert result.structured_content is not None
    assert result.structured_content["ready"] is True
    assert "runtime_root" not in result.structured_content
    assert "daemon" not in result.structured_content
    assert result.meta is not None
    assert set(result.meta) == {"io.modelcontextprotocol/serverInfo"}
    server_info = result.meta["io.modelcontextprotocol/serverInfo"]
    assert isinstance(server_info, dict)
    assert server_info["name"] == "jazn-runtime"


def test_http_app_contains_mcp_liveness_and_readiness_routes(tmp_path: Path) -> None:
    gateway = _gateway(tmp_path, _FakeBackend())
    app = gateway.asgi_app()
    paths = {getattr(route, "path", None) for route in app.routes}
    assert MCP_PATH in paths
    assert HEALTH_PATH in paths
    assert READINESS_PATH in paths


@pytest.mark.anyio
async def test_generate_rate_limit_is_operation_specific_and_fail_closed(tmp_path: Path) -> None:
    gateway = _gateway(tmp_path, _FakeBackend())
    async with Client(gateway.mcp, raise_exceptions=True) as client:
        for index in range(10):
            result = await client.call_tool(
                "jazn_generate_visible_reply",
                {"request_id": f"req-rate-{index}", "message": "hello"},
            )
            assert result.is_error is False
        limited = await client.call_tool(
            "jazn_generate_visible_reply",
            {"request_id": "req-rate-10", "message": "hello"},
        )

    assert limited.is_error is True
    assert limited.structured_content is not None
    assert limited.structured_content["reason"] == "rate_limit_exceeded"
