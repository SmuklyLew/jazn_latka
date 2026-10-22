"""Public MCP introspection MUST reject incomplete token-boundary claims."""
from __future__ import annotations

import asyncio
import json
import time
from types import SimpleNamespace
from typing import Any

import pytest

from latka_jazn.mcp.oauth_introspection import (
    IntrospectionVerifierConfig,
    Rfc7662TokenVerifier,
)

ISSUER = "https://jazn-auth-staging.example.test"
RESOURCE = "https://jazn-runtime-staging.example.test/mcp"


class _Response:
    status = 200

    def __init__(self, payload: dict[str, Any]) -> None:
        self.body = json.dumps(payload).encode("utf-8")

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self, _limit: int) -> bytes:
        return self.body


def _verify(payload: dict[str, Any]) -> Any | None:
    cfg = IntrospectionVerifierConfig(
        introspection_url=f"{ISSUER}/oauth/introspect",
        issuer_url=ISSUER,
        resource_server_url=RESOURCE,
        client_id="isolated-introspection-client",
        client_secret="test-only-not-a-real-secret",
    )
    verifier = Rfc7662TokenVerifier(
        cfg,
        access_token_factory=lambda **fields: SimpleNamespace(**fields),
        http_open=lambda _request, timeout: _Response(payload),
    )
    return asyncio.run(verifier.verify_token("fake-access-token"))


def _valid() -> dict[str, Any]:
    return {
        "active": True,
        "iss": ISSUER,
        "aud": RESOURCE,
        "exp": int(time.time()) + 600,
        "client_id": "chatgpt-staging",
        "scope": "jazn:mcp:connect jazn:status:read",
    }


def test_valid_token_claims_are_bound_to_staging_resource() -> None:
    token = _verify(_valid())
    assert token is not None
    assert token.resource == RESOURCE
    assert "jazn:mcp:connect" in token.scopes
    assert token.expires_at > time.time()


@pytest.mark.parametrize(
    ("key", "replacement"),
    [
        ("iss", None),
        ("iss", ""),
        ("iss", "https://jazn-auth.example.test"),
        ("aud", "https://jazn-runtime.example.test/mcp"),
        ("exp", None),
        ("exp", "9999999999"),
        ("exp", True),
        ("exp", 0),
        ("scope", ""),
        ("scope", "jazn:status:read"),
        ("client_id", ""),
    ],
)
def test_incomplete_or_mismatched_claims_fail_closed(key: str, replacement: Any) -> None:
    payload = _valid()
    if replacement is None:
        payload.pop(key)
    else:
        payload[key] = replacement
    assert _verify(payload) is None


def test_expired_token_is_not_authorized() -> None:
    assert _verify({**_valid(), "exp": int(time.time()) - 1}) is None


def test_inactive_token_is_not_authorized() -> None:
    assert _verify({**_valid(), "active": False}) is None
