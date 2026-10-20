from __future__ import annotations

from tools.chatgpt_oauth_live_preflight import ISSUER, RESOURCE, probe


def responses(*, configured=True, pkce=True, challenge=True, wrong_resource=False):
    resource_origin = RESOURCE.removesuffix("/mcp")
    data = {
        ISSUER + "/healthz": (200 if configured else 503, {}, {"deployment_configured": configured}),
        resource_origin + "/.well-known/oauth-protected-resource": (
            200, {}, {"resource": "https://wrong.example/mcp" if wrong_resource else RESOURCE,
                      "authorization_servers": [ISSUER]}),
        ISSUER + "/.well-known/oauth-authorization-server": (
            200, {}, {"issuer": ISSUER, "code_challenge_methods_supported": ["S256"] if pkce else [],
                      "authorization_endpoint": ISSUER + "/authorize",
                      "token_endpoint": ISSUER + "/oauth/token",
                      "client_id_metadata_document_supported": True}),
        RESOURCE: (401 if challenge else 503, {
            "www-authenticate": "Bearer resource_metadata=\"" +
            resource_origin + "/.well-known/oauth-protected-resource\""
        } if challenge else {}, {}),
    }
    return lambda url: data[url]


def test_external_mcp_preflight_never_promotes_live_turn_readiness():
    value = probe(responses())
    assert value["ok"] is True
    assert not value["accepted_turns_tested"]
    assert not value["daemon_ready_tested"]
    assert not value["authenticated_tools_list_tested"]
    assert not value["production_activation_authorized"]


def test_preflight_fails_closed_for_unconfigured_auth_and_missing_pkce():
    for kwargs in ({"configured": False}, {"pkce": False}, {"challenge": False},
                   {"wrong_resource": True}):
        value = probe(responses(**kwargs))
        assert value["ok"] is False
        assert value["blockers"]


def test_preflight_transport_error_is_not_mistaken_for_authorization():
    def broken(_):
        raise TimeoutError("blocked")
    value = probe(broken)
    assert not value["ok"]
    assert value["blockers"] == ["probe_transport_or_metadata_error"]
