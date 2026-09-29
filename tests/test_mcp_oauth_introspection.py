from __future__ import annotations

import asyncio
import base64
import json

import pytest

from latka_jazn.mcp.oauth_introspection import (
    IntrospectionVerifierConfig,
    Rfc7662TokenVerifier,
)


class _Response:
    def __init__(self, payload: dict[str, object], status: int = 200) -> None:
        self.status = status
        self._body = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def read(self, _limit: int) -> bytes:
        return self._body


class _Token:
    def __init__(self, **kwargs: object) -> None:
        self.__dict__.update(kwargs)


def _config() -> IntrospectionVerifierConfig:
    return IntrospectionVerifierConfig(
        introspection_url="https://id.example.test/oauth2/introspect",
        issuer_url="https://id.example.test/",
        resource_server_url="https://jazn.example.test/mcp",
        client_id="resource-client",
        client_secret="secret:value",
    )


def test_config_rejects_non_https_and_hides_secret_in_repr() -> None:
    config = _config()
    assert "secret:value" not in repr(config)
    with pytest.raises(ValueError, match="introspection_url_must_be_absolute_https_url"):
        IntrospectionVerifierConfig(
            introspection_url="http://id.example.test/introspect",
            issuer_url="https://id.example.test/",
            resource_server_url="https://jazn.example.test/mcp",
            client_id="client",
            client_secret="secret",
        )


def test_active_introspection_response_becomes_bound_access_token() -> None:
    captured: dict[str, object] = {}

    def http_open(req, timeout: float):
        captured["authorization"] = req.headers["Authorization"]
        captured["body"] = req.data
        captured["timeout"] = timeout
        return _Response(
            {
                "active": True,
                "client_id": "chatgpt-client",
                "scope": "jazn:mcp:connect jazn:turn:submit",
                "aud": ["another-resource", "https://jazn.example.test/mcp"],
                "sub": "user-123",
                "iss": "https://id.example.test",
                "exp": 2_000_000_000,
            }
        )

    verifier = Rfc7662TokenVerifier(_config(), access_token_factory=_Token, http_open=http_open)
    token = asyncio.run(verifier.verify_token("opaque-token"))
    assert token is not None
    assert token.client_id == "chatgpt-client"
    assert token.resource == "https://jazn.example.test/mcp"
    assert token.subject == "user-123"
    assert token.scopes == ["jazn:mcp:connect", "jazn:turn:submit"]
    assert token.claims == {"iss": "https://id.example.test"}
    expected_basic = base64.b64encode(b"resource-client:secret:value").decode("ascii")
    assert captured["authorization"] == f"Basic {expected_basic}"
    assert b"opaque-token" in captured["body"]


@pytest.mark.parametrize(
    "payload",
    [
        {"active": False},
        {"active": True, "client_id": "chatgpt-client", "aud": "https://other.example.test/mcp"},
        {
            "active": True,
            "client_id": "chatgpt-client",
            "aud": "https://jazn.example.test/mcp",
            "iss": "https://wrong.example.test",
        },
        {"active": True, "aud": "https://jazn.example.test/mcp"},
    ],
)
def test_introspection_fails_closed(payload: dict[str, object]) -> None:
    verifier = Rfc7662TokenVerifier(
        _config(),
        access_token_factory=_Token,
        http_open=lambda _req, timeout: _Response(payload),
    )
    assert asyncio.run(verifier.verify_token("opaque-token")) is None
