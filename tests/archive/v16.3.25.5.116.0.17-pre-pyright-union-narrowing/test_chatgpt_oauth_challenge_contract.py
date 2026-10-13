from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest

pytest.importorskip("mcp")
from mcp.server.auth.provider import TokenVerifier

from latka_jazn.mcp.http_gateway import (
    PublicMcpGateway, _Principal, SCOPE_CONNECT, SCOPE_STATUS_READ,
    build_public_mcp_gateway,
)


class _NoBackendCalls:
    def call_tool(
        self, name: str, arguments: dict[str, Any],
        *, meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        raise AssertionError("Unauthenticated or insufficient-scope calls cannot reach the backend")


def _oauth_gateway(tmp_path: Path) -> PublicMcpGateway:
    return build_public_mcp_gateway(
        root=tmp_path,
        backend=_NoBackendCalls(),
        token_verifier=cast(TokenVerifier, object()),
        oauth_issuer_url="https://id.example.test",
        oauth_resource_server_url="https://jazn.example.test/mcp",
    )


@pytest.mark.anyio
async def test_missing_identity_triggers_bounded_login_challenge(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    gateway = _oauth_gateway(tmp_path)
    monkeypatch.setattr(gateway, "_principal", lambda: None)
    result = await gateway.mcp.call_tool("jazn_status", {})
    assert result.is_error is True
    assert result.structured_content is not None
    assert result.structured_content["reason"] == "authenticated_principal_required"
    assert result.meta is not None
    challenge = result.meta["mcp/www_authenticate"]
    assert len(challenge) == 1
    assert 'error="invalid_token"' in challenge[0]
    assert 'error_description="' in challenge[0]
    assert 'resource_metadata="https://jazn.example.test/.well-known/oauth-protected-resource"' in challenge[0]


@pytest.mark.anyio
async def test_insufficient_scope_includes_auth_challenge_but_no_memory_access(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    gateway = _oauth_gateway(tmp_path)
    monkeypatch.setattr(
        gateway, "_principal", lambda: _Principal(subject="test", scopes=frozenset({SCOPE_CONNECT})),
    )
    result = await gateway.mcp.call_tool("jazn_status", {})
    assert result.is_error is True
    assert result.structured_content is not None
    assert result.structured_content["reason"] == "insufficient_scope"
    assert result.meta is not None
    assert 'error="insufficient_scope"' in result.meta["mcp/www_authenticate"][0]


@pytest.mark.anyio
async def test_developer_loopback_errors_never_advertise_remote_oauth(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    gateway = build_public_mcp_gateway(
        root=tmp_path, backend=_NoBackendCalls(), allow_unauthenticated_loopback_dev=True,
    )
    monkeypatch.setattr(gateway, "_principal", lambda: None)
    result = await gateway.mcp.call_tool("jazn_status", {})
    assert result.is_error is True
    assert result.meta is None or "mcp/www_authenticate" not in result.meta


def test_non_auth_errors_never_create_oauth_challenge(tmp_path: Path) -> None:
    gateway = _oauth_gateway(tmp_path)
    assert gateway._auth_challenge(error="rate_limit_exceeded") is None
    assert gateway._auth_challenge(error="bad_arguments") is None
    assert gateway._auth_challenge(error="invalid_token") is not None
