"""Read-only, no-secrets external OAuth/MCP preflight.

Validates public discovery, canonical issuer/resource, S256 and the initial
unauthenticated 401 challenge. A passing result does NOT prove logged-in
tools/list, daemon readiness or accepted turns. No OAuth tokens are read.
"""
from __future__ import annotations

import json
import sys
from collections.abc import Callable
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

ISSUER = "https://jazn-auth.jazn-lakta.workers.dev"
RESOURCE = "https://jazn-runtime.jazn-lakta.workers.dev/mcp"
_MAX_BYTES = 65536


class _NeverRedirect(HTTPRedirectHandler):
    def redirect_request(self, req: Any, fp: Any, code: int, msg: str,
                         headers: Any, newurl: str) -> None:
        return None


def fetch(url: str) -> tuple[int, dict[str, str], dict[str, Any]]:
    # Only trusted, fixed HTTPS origins above are called; no URL user input.
    if not url.startswith((ISSUER + "/", RESOURCE.removesuffix("/mcp") + "/")):
        raise ValueError("untrusted_oauth_probe_origin")
    request = Request(url, headers={"Accept": "application/json, text/event-stream"}, method="GET")
    try:
        with build_opener(_NeverRedirect()).open(request, timeout=8) as reply:
            raw = reply.read(_MAX_BYTES + 1)
            status, headers = reply.status, dict(reply.headers.items())
    except HTTPError as exc:
        # Expected HTTP 401 and staged 503 are meaningful negative evidence.
        raw = exc.read(_MAX_BYTES + 1)
        status, headers = exc.code, dict(exc.headers.items())
    if len(raw) > _MAX_BYTES:
        raise ValueError("oauth_probe_response_too_large")
    try:
        body = json.loads(raw.decode("utf-8"))
    except (UnicodeError, ValueError):
        body = {}
    return status, {k.lower(): v for k, v in headers.items()}, body if isinstance(body, dict) else {}


def probe(get: Callable[[str], tuple[int, dict[str, str], dict[str, Any]]] = fetch) -> dict[str, Any]:
    details: dict[str, bool] = {}
    errors: list[str] = []

    def check(label: str, accepted: bool) -> None:
        details[label] = bool(accepted)
        if not accepted:
            errors.append(label)

    try:
        auth_health, _, health = get(ISSUER + "/healthz")
        check("auth_deployment_configured", auth_health == 200 and health.get("deployment_configured") is True)
        protected_status, _, protected = get(RESOURCE.removesuffix("/mcp") + "/.well-known/oauth-protected-resource")
        check("resource_metadata", protected_status == 200 and
              protected.get("resource") == RESOURCE and
              ISSUER in protected.get("authorization_servers", []))
        auth_status, _, authorization = get(ISSUER + "/.well-known/oauth-authorization-server")
        check("authorization_metadata", auth_status == 200 and
              authorization.get("issuer") == ISSUER and
              "S256" in authorization.get("code_challenge_methods_supported", []) and
              authorization.get("authorization_endpoint", "").startswith(ISSUER + "/") and
              authorization.get("token_endpoint", "").startswith(ISSUER + "/") and
              (authorization.get("client_id_metadata_document_supported") is True or
               isinstance(authorization.get("registration_endpoint"), str)))
        unauth_status, unauth_headers, _ = get(RESOURCE)
        challenge = unauth_headers.get("www-authenticate", "")
        check("unauthenticated_mcp_401", unauth_status == 401 and
              challenge.lower().lstrip().startswith("bearer ") and
              'resource_metadata="' + RESOURCE.removesuffix("/mcp") + '/.well-known/oauth-protected-resource"' in challenge)
    except (OSError, URLError, TimeoutError, ValueError, TypeError, KeyError):
        errors.append("probe_transport_or_metadata_error")
    return {
        "ok": bool(details) and all(details.values()) and not errors,
        "issuer": ISSUER, "resource": RESOURCE,
        "checks": details, "blockers": errors,
        "authenticated_tools_list_tested": False,
        "daemon_ready_tested": False,
        "accepted_turns_tested": False,
        "production_activation_authorized": False,
    }


def main() -> int:
    result = probe()
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
