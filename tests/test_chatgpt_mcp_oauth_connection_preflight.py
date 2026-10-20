"""Read-only ChatGPT OAuth discovery and current-message evidence boundaries."""
from __future__ import annotations

import json

from latka_jazn.mcp.oauth_preflight import HttpObservation, inspect_chatgpt_oauth_mcp

ENDPOINT = "https://jazn.example.com/mcp"
ISSUER = "https://id.example.com"
META = "https://jazn.example.com/.well-known/oauth-protected-resource/mcp"
AS_META = ISSUER + "/.well-known/oauth-authorization-server"


def _json(value: object, status: int = 200, headers: dict[str, str] | None = None) -> HttpObservation:
    return HttpObservation(status, headers or {}, json.dumps(value).encode())


def _request(
    *,
    scope_mismatch: bool = False,
    no_pkce: bool = False,
    missing_challenge: bool = False,
    no_registration: bool = False,
    no_401: bool = False,
):
    seen: list[tuple[str, str, bytes | None]] = []

    def request(url: str, method: str, body: bytes | None) -> HttpObservation:
        seen.append((url, method, body))
        if url == ENDPOINT:
            return _json({}, status=200 if no_401 else 401, headers=(
                {} if missing_challenge else {
                    "WWW-Authenticate": f'Bearer resource_metadata="{META}", error="invalid_token"'
                }
            ))
        if url == META:
            return _json({
                "resource": "https://other.example.com/mcp" if scope_mismatch else ENDPOINT,
                "authorization_servers": [ISSUER],
            })
        if url == AS_META:
            value: dict[str, object] = {
                "issuer": ISSUER,
                "authorization_endpoint": ISSUER + "/oauth/authorize",
                "token_endpoint": ISSUER + "/oauth/token",
                "code_challenge_methods_supported": [] if no_pkce else ["S256"],
            }
            if not no_registration:
                value["client_id_metadata_document_supported"] = True
            return _json(value)
        return _json({}, status=404)

    return request, seen


def test_complete_oauth_metadata_is_discovery_only() -> None:
    request, seen = _request()
    result = inspect_chatgpt_oauth_mcp(ENDPOINT, request=request)
    assert result["ok"] is True, result["blockers"]
    assert result["registration_mode"] == "cimd"
    assert result["oauth_login_verified"] is False
    assert result["chatgpt_connection_verified"] is False
    assert result["current_message_tool_invocation_verified"] is False
    assert result["accepted_visible_turn_verified"] is False
    assert seen[0][0] == ENDPOINT
    assert seen[0][1] == "POST"
    assert b"tools/list" in (seen[0][2] or b"")
    assert len(seen) == 3


def test_rejects_localhost_without_network() -> None:
    calls: list[str] = []
    result = inspect_chatgpt_oauth_mcp(
        "http://127.0.0.1:8080/mcp",
        request=lambda u, method, data: calls.append(u),  # type: ignore[arg-type]
    )
    assert result["ok"] is False
    assert not calls
    assert result["checks"]["public_https_mcp_url"] is False


def test_rejects_wrong_resource_audience() -> None:
    request, _ = _request(scope_mismatch=True)
    result = inspect_chatgpt_oauth_mcp(ENDPOINT, request=request)
    assert not result["ok"]
    assert "resource_audience_mismatch" in result["blockers"]


def test_rejects_oauth_without_pkce_s256() -> None:
    request, _ = _request(no_pkce=True)
    result = inspect_chatgpt_oauth_mcp(ENDPOINT, request=request)
    assert not result["ok"]
    assert "oauth_pkce_s256_missing" in result["blockers"]


def test_rejects_missing_bearer_auth_challenge() -> None:
    request, _ = _request(missing_challenge=True)
    result = inspect_chatgpt_oauth_mcp(ENDPOINT, request=request)
    assert not result["ok"]
    assert "bearer_resource_metadata_challenge_missing" in result["blockers"]


def test_rejects_unprotected_mcp_endpoint() -> None:
    request, _ = _request(no_401=True)
    result = inspect_chatgpt_oauth_mcp(ENDPOINT, request=request)
    assert not result["ok"]
    assert "mcp_did_not_require_oauth" in result["blockers"]


def test_pre_registered_client_must_be_provisioned_separately() -> None:
    request, _ = _request(no_registration=True)
    result = inspect_chatgpt_oauth_mcp(ENDPOINT, request=request)
    assert not result["ok"]
    assert result["registration_mode"] == "provided_client_required"


def test_root_metadata_fallback_is_supported() -> None:
    request, seen = _request()

    def fallback(url: str, method: str, data: bytes | None) -> HttpObservation:
        if url == META:
            return _json({}, status=404)
        if url == "https://jazn.example.com/.well-known/oauth-protected-resource":
            return _json({"resource": ENDPOINT, "authorization_servers": [ISSUER]})
        # Deliberately omit challenge location; this remains fail-closed.
        return request(url, method, data)

    result = inspect_chatgpt_oauth_mcp(ENDPOINT, request=fallback)
    assert result["ok"] is True, result["blockers"]
    assert seen and seen[0][0] == ENDPOINT


def test_network_errors_are_redacted_and_fail_closed() -> None:
    def down(url: str, method: str, data: bytes | None) -> HttpObservation:
        raise OSError("token=sensitive-secret")
    result = inspect_chatgpt_oauth_mcp(ENDPOINT, request=down)
    serialized = json.dumps(result)
    assert "sensitive-secret" not in serialized
    assert result["ok"] is False
    assert "unauthenticated_mcp_request_failed" in result["blockers"]
