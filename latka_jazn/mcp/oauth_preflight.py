from __future__ import annotations

"""Read-only, dependency-free OAuth discovery preflight for remote ChatGPT MCP.

This probes public metadata and an unauthenticated challenge. It neither
acquires credentials nor verifies that ChatGPT has selected/called Jaźń.
"""

import argparse
from dataclasses import dataclass
import ipaddress
import json
import re
from typing import Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

SCHEMA = "jazn_chatgpt_oauth_connection_preflight/v1"
MAX_BYTES = 32_768
TIMEOUT_SECONDS = 6.0
CHALLENGE_URL = re.compile(r'\bresource_metadata\s*=\s*"([^"]+)"', re.IGNORECASE)


@dataclass(frozen=True)
class HttpObservation:
    status: int
    headers: Mapping[str, str]
    body: bytes


RequestFunction = Callable[[str, str, bytes | None], HttpObservation]


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        return None


def _public_https_url(value: str, *, mcp_endpoint: bool = False) -> str:
    if not isinstance(value, str) or value != value.strip():
        raise ValueError("invalid_https_url")
    parts = urlsplit(value)
    host = (parts.hostname or "").lower()
    if (
        parts.scheme != "https" or not host or not parts.netloc
        or parts.username is not None or parts.password is not None
        or parts.fragment or parts.query
        or host in {"localhost", "localhost.localdomain"}
        or host.endswith((".local", ".internal", ".localhost"))
    ):
        raise ValueError("public_https_url_required")
    try:
        ip = ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        pass
    else:
        if not ip.is_global:
            raise ValueError("public_https_url_required")
    if mcp_endpoint and parts.path != "/mcp":
        raise ValueError("mcp_endpoint_must_end_with_slash_mcp")
    return value


def _request(url: str, method: str, data: bytes | None) -> HttpObservation:
    request = Request(
        url, data=data, method=method,
        headers={
            "Accept": "application/json, text/event-stream" if method == "POST" else "application/json",
            "Content-Type": "application/json",
            "MCP-Protocol-Version": "2026-07-28",
        },
    )
    opener = build_opener(_NoRedirect)
    try:
        with opener.open(request, timeout=TIMEOUT_SECONDS) as response:
            status = int(response.status)
            headers = dict(response.headers.items())
            body = response.read(MAX_BYTES + 1)
    except HTTPError as error:
        status = int(error.code)
        headers = dict(error.headers.items()) if error.headers else {}
        body = error.read(MAX_BYTES + 1)
        error.close()
    if len(body) > MAX_BYTES:
        raise ValueError("oauth_metadata_response_too_large")
    return HttpObservation(status, headers, body)


def _header(headers: Mapping[str, str], name: str) -> str:
    return next((str(v) for k, v in headers.items() if k.lower() == name.lower()), "")


def _json_obj(response: HttpObservation) -> dict[str, object] | None:
    if response.status != 200 or len(response.body) > MAX_BYTES:
        return None
    try:
        value = json.loads(response.body)
    except (ValueError, UnicodeError):
        return None
    return value if isinstance(value, dict) else None


def inspect_chatgpt_oauth_mcp(
    endpoint: str,
    *,
    request: RequestFunction = _request,
) -> dict[str, object]:
    """Inspect discovery only; never send credentials or invoke Jaźń tools."""
    checks: dict[str, bool] = {
        "public_https_mcp_url": False,
        "unauthenticated_mcp_401": False,
        "bearer_resource_metadata_challenge": False,
        "protected_resource_metadata": False,
        "resource_audience_matches_endpoint": False,
        "authorization_server_metadata": False,
        "authorization_server_issuer_matches": False,
        "authorization_code_pkce_s256": False,
        "https_oauth_endpoints": False,
        "chatgpt_client_registration_supported": False,
    }
    report: dict[str, object] = {
        "schema_version": SCHEMA,
        "ok": False,
        "checks": checks,
        "blockers": [],
        "registration_mode": None,
        "oauth_login_verified": False,
        "chatgpt_connection_verified": False,
        "current_message_tool_invocation_verified": False,
        "accepted_visible_turn_verified": False,
        "truth_boundary": (
            "This check verifies only public OAuth discovery and an anonymous 401 challenge. "
            "It does not authenticate a user, connect ChatGPT, invoke an MCP tool, "
            "or establish an accepted display_exact conversation turn."
        ),
    }

    def fail(code: str) -> None:
        blockers = report["blockers"]
        assert isinstance(blockers, list)
        if code not in blockers:
            blockers.append(code)

    try:
        url = _public_https_url(endpoint, mcp_endpoint=True)
    except ValueError as exc:
        fail(str(exc))
        return report
    checks["public_https_mcp_url"] = True
    parsed = urlsplit(url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    request_body = b'{"jsonrpc":"2.0","id":"auth-preflight","method":"tools/list","params":{}}'

    try:
        unauthorized = request(url, "POST", request_body)
    except (OSError, ValueError, URLError):
        fail("unauthenticated_mcp_request_failed")
        return report
    checks["unauthenticated_mcp_401"] = unauthorized.status == 401
    if not checks["unauthenticated_mcp_401"]:
        fail("mcp_did_not_require_oauth")

    challenge = _header(unauthorized.headers, "WWW-Authenticate")
    match = CHALLENGE_URL.search(challenge) if challenge.lower().startswith("bearer ") else None
    metadata_urls: list[str] = []
    if match:
        try:
            candidate = _public_https_url(match.group(1))
            p = urlsplit(candidate)
            if (p.scheme, p.netloc) != (parsed.scheme, parsed.netloc) or not p.path.startswith("/.well-known/oauth-protected-resource"):
                raise ValueError("unexpected_resource_metadata_origin")
            metadata_urls.append(candidate)
            checks["bearer_resource_metadata_challenge"] = True
        except ValueError:
            fail("invalid_resource_metadata_challenge")
    else:
        fail("bearer_resource_metadata_challenge_missing")

    for candidate in (
        origin + "/.well-known/oauth-protected-resource/mcp",
        origin + "/.well-known/oauth-protected-resource",
    ):
        if candidate not in metadata_urls:
            metadata_urls.append(candidate)

    resource: dict[str, object] | None = None
    for candidate in metadata_urls:
        try:
            resource = _json_obj(request(candidate, "GET", None))
        except (OSError, ValueError, URLError):
            resource = None
        if resource is not None:
            break
    checks["protected_resource_metadata"] = resource is not None
    if resource is None:
        fail("protected_resource_metadata_unavailable")
        return report
    checks["resource_audience_matches_endpoint"] = resource.get("resource") == url
    if not checks["resource_audience_matches_endpoint"]:
        fail("resource_audience_mismatch")

    servers = resource.get("authorization_servers")
    issuer: str | None = None
    if isinstance(servers, list) and servers and isinstance(servers[0], str):
        try:
            issuer = _public_https_url(servers[0])
        except ValueError:
            pass
    if issuer is None:
        fail("authorization_server_url_invalid")
        return report

    # RFC 8414 supports pathful issuers by inserting the well-known segment.
    parts = urlsplit(issuer)
    base = f"{parts.scheme}://{parts.netloc}"
    suffix = parts.path.rstrip("/")
    candidates = (
        base + "/.well-known/oauth-authorization-server" + suffix,
        base + suffix + "/.well-known/openid-configuration",
    )
    authorization: dict[str, object] | None = None
    for candidate in candidates:
        try:
            authorization = _json_obj(request(candidate, "GET", None))
        except (OSError, ValueError, URLError):
            authorization = None
        if authorization is not None:
            break
    checks["authorization_server_metadata"] = authorization is not None
    if authorization is None:
        fail("authorization_server_metadata_unavailable")
        return report

    checks["authorization_server_issuer_matches"] = authorization.get("issuer") == issuer
    if not checks["authorization_server_issuer_matches"]:
        fail("authorization_issuer_mismatch")
    challenge_methods = authorization.get("code_challenge_methods_supported")
    checks["authorization_code_pkce_s256"] = isinstance(challenge_methods, list) and "S256" in challenge_methods
    if not checks["authorization_code_pkce_s256"]:
        fail("oauth_pkce_s256_missing")
    try:
        endpoints = (authorization["authorization_endpoint"], authorization["token_endpoint"])
        if any(not isinstance(item, str) for item in endpoints):
            raise ValueError("invalid_endpoint")
        for item in endpoints:
            _public_https_url(str(item))
        checks["https_oauth_endpoints"] = True
    except (KeyError, ValueError):
        fail("oauth_authorization_or_token_endpoint_missing")

    cimd = authorization.get("client_id_metadata_document_supported") is True
    dcr = isinstance(authorization.get("registration_endpoint"), str)
    if dcr:
        try:
            _public_https_url(str(authorization["registration_endpoint"]))
        except ValueError:
            dcr = False
    checks["chatgpt_client_registration_supported"] = cimd or dcr
    report["registration_mode"] = "cimd" if cimd else ("dcr" if dcr else "provided_client_required")
    if not checks["chatgpt_client_registration_supported"]:
        fail("configure_pre_registered_oauth_client_in_chatgpt")

    for key, accepted in checks.items():
        if not accepted and key not in {"bearer_resource_metadata_challenge", "chatgpt_client_registration_supported"}:
            fail(key)
    # A pre-registered client is supported, but must be provisioned separately;
    # no false "ready" when the tool cannot verify the actual connection.
    report["ok"] = (
        all(checks.values())
        and report["registration_mode"] in {"cimd", "dcr"}
    )
    return report


def run_oauth_preflight_cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="run.py mcp-auth-preflight", allow_abbrev=False,
        description="Read-only OAuth discovery for a public Jaźń MCP endpoint.",
    )
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--json", action="store_true")
    ns = parser.parse_args(argv)
    result = inspect_chatgpt_oauth_mcp(ns.endpoint)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(run_oauth_preflight_cli())
