from __future__ import annotations

import uuid
from urllib.parse import parse_qs, urlencode, urlsplit

import pytest

from latka_jazn.model_adapters.siwc_oauth_flow import (
    AUTHORIZATION_URL, ISSUER, RESOURCE, TOKEN_URL,
    begin_login, consume_callback, verify_token_response,
)

HOST = "urn:uuid:" + str(uuid.UUID("9aeef7c8-6004-4982-a6fd-72be02454165"))


def test_siwc_browser_flow_uses_separate_openai_resource_and_real_pkce():
    first = begin_login(host_id=HOST, port=1455)
    second = begin_login(host_id=HOST, port=1455)
    assert first.authorization_url.startswith(AUTHORIZATION_URL + "?")
    params = parse_qs(urlsplit(first.authorization_url).query)
    assert params["client_id"] == ["dynamic_agent_client"]
    assert params["ext_agent_host_id"] == [HOST]
    assert params["resource"] == [RESOURCE]
    assert params["redirect_uri"] == ["http://127.0.0.1:1455/auth/callback"]
    assert params["code_challenge_method"] == ["S256"]
    assert "agent_name_hint" in params
    assert first.state != second.state and first.verifier != second.verifier
    assert ISSUER != "https://jazn-auth.jazn-lakta.workers.dev"
    assert TOKEN_URL.endswith("/api/accounts/oauth/token")


def test_siwc_callback_accepts_only_one_time_exact_local_redirect_and_issued_id():
    a = begin_login(host_id=HOST, port=1455)
    url = a.redirect_uri + "?" + urlencode({"code": "some-code", "client_id": "oaiapp_abc", "state": a.state})
    g = consume_callback(a, url)
    form = g.token_form()
    assert form["client_id"] == "oaiapp_abc"
    assert form["resource"] == RESOURCE
    assert form["code_verifier"] == a.verifier
    with pytest.raises(ValueError, match="already_consumed"):
        consume_callback(a, url)


@pytest.mark.parametrize("mutator", [
    lambda a: "http://localhost:1455/auth/callback?" + urlencode({"code": "c", "client_id": "oaiapp_abc", "state": a.state}),
    lambda a: a.redirect_uri + "?" + urlencode({"code": "c", "client_id": "oaiapp_abc", "state": "wrong"}),
    lambda a: a.redirect_uri + "?" + urlencode({"code": "c", "state": a.state}),
    lambda a: a.redirect_uri + "?" + urlencode({"error": "access_denied", "state": a.state}),
    lambda a: a.redirect_uri + "?" + urlencode({"code": "c", "client_id": "oaiapp_abc", "state": a.state}) + "&state=duplicate",
])
def test_siwc_invalid_callback_fails_closed(mutator):
    a = begin_login(host_id=HOST, port=1455)
    with pytest.raises(ValueError):
        consume_callback(a, mutator(a))


def test_siwc_returning_client_omits_registration_hint_and_refuses_switch():
    a = begin_login(host_id=HOST, port=1455, client_id="oaiapp_registered")
    params = parse_qs(urlsplit(a.authorization_url).query)
    assert params["client_id"] == ["oaiapp_registered"]
    assert "agent_name_hint" not in params
    bad = a.redirect_uri + "?" + urlencode({"code": "c", "client_id": "oaiapp_other", "state": a.state})
    with pytest.raises(ValueError, match="client_id_mismatch"):
        consume_callback(a, bad)


def test_siwc_unsigned_or_incomplete_tokens_are_never_authorized():
    a = begin_login(host_id=HOST, port=1455)
    g = consume_callback(a, a.redirect_uri + "?" + urlencode({
        "code": "c", "client_id": "oaiapp_abc", "state": a.state
    }))
    with pytest.raises(ValueError, match="scope_not_granted"):
        verify_token_response(g, {"scope": "openid profile"})
    with pytest.raises(ValueError, match="incomplete"):
        verify_token_response(g, {
            "scope": "chatgpt.tokens.use.direct", "token_type": "Bearer", "expires_in": 3600,
        })
    with pytest.raises(ValueError, match="verification_failed"):
        verify_token_response(g, {
            "scope": "chatgpt.tokens.use.direct", "token_type": "Bearer", "expires_in": 3600,
            "access_token": "not-jwt", "refresh_token": "not-jwt", "id_token": "not-a-signed-jwt",
        })


def test_siwc_invalid_host_and_port_are_rejected():
    for kwargs in ({"host_id": "invalid", "port": 1455}, {"host_id": HOST, "port": 0},
                   {"host_id": HOST, "port": 1455, "client_id": "dynamic_agent_client"}):
        with pytest.raises(ValueError):
            begin_login(**kwargs)
