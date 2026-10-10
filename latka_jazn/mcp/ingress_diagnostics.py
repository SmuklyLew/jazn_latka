from __future__ import annotations

"""Read-only MCP protocol-era probe. Never proves ChatGPT tool exposure.

Modern 2026-07-28 servers use server/discover and request-scoped metadata.
Legacy servers can be diagnosed via initialize (2025-11-25), but only after
an unrecognized HTTP 4xx response. No redirects, credentials or user turns.
"""

import json
from typing import Any
import urllib.error
import urllib.request
from urllib.parse import urlsplit

MODERN_PROTOCOL_VERSION = "2026-07-28"
LEGACY_PROTOCOL_VERSION = "2025-11-25"
_MAX_RESPONSE_BYTES = 65536


class _RejectRedirects(urllib.request.HTTPRedirectHandler):
    """A validated /mcp endpoint must never redirect a diagnostic POST."""

    def redirect_request(
        self, req: urllib.request.Request, fp: Any, code: int,
        msg: str, headers: Any, newurl: str,
    ) -> None:
        return None


def validate_probe_url(value: str) -> str:
    candidate = str(value or "").strip()
    parsed = urlsplit(candidate)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("mcp_probe_invalid_url")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("mcp_probe_url_must_not_contain_credentials_or_query")
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("mcp_probe_invalid_port") from exc
    if port is not None and not 1 <= port <= 65535:
        raise ValueError("mcp_probe_invalid_port")
    if parsed.path != "/mcp":
        raise ValueError("mcp_probe_path_must_be_/mcp")
    if parsed.scheme == "http" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("mcp_probe_public_endpoint_requires_https")
    return candidate


def _probe_request(endpoint: str, *, modern: bool) -> urllib.request.Request:
    if modern:
        body = {
            "jsonrpc": "2.0", "id": 1, "method": "server/discover",
            "params": {"_meta": {
                "io.modelcontextprotocol/protocolVersion": MODERN_PROTOCOL_VERSION,
                "io.modelcontextprotocol/clientInfo": {
                    "name": "jazn-mcp-preflight", "version": "1",
                },
                "io.modelcontextprotocol/clientCapabilities": {},
            }},
        }
    else:
        body = {
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {
                "protocolVersion": LEGACY_PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "jazn-mcp-preflight", "version": "1"},
            },
        }
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    if modern:
        headers["MCP-Protocol-Version"] = MODERN_PROTOCOL_VERSION
        headers["Mcp-Method"] = "server/discover"
    return urllib.request.Request(
        endpoint, data=json.dumps(body).encode("utf-8"), method="POST",
        headers=headers,
    )


def _round_trip(
    endpoint: str, base: dict[str, Any], *, modern: bool, timeout: float,
) -> dict[str, Any]:
    era = "modern" if modern else "legacy"
    response_base = {**base, "protocol_era": era}
    request = _probe_request(endpoint, modern=modern)
    # The default urlopen() follows redirects (and can change POST to GET).
    # Reject them before any second request is made, including same-host 307/308.
    opener = urllib.request.build_opener(_RejectRedirects())
    try:
        with opener.open(request, timeout=timeout) as response:
            status = int(response.status)
            if status != 200:
                return {**response_base, "ok": False, "http_status": status,
                        "reason": "mcp_probe_unexpected_http_status"}
            geturl = getattr(response, "geturl", None)
            if callable(geturl) and geturl() != endpoint:
                return {**response_base, "ok": False, "http_status": status,
                        "reason": "mcp_http_redirect_rejected"}
            media = str(response.headers.get("Content-Type", "")).lower()
            if "text/event-stream" in media:
                return {**response_base, "ok": False, "http_status": status,
                        "reason": "mcp_sse_requires_protocol_inspector"}
            if "application/json" not in media:
                return {**response_base, "ok": False, "http_status": status,
                        "reason": "mcp_unexpected_content_type"}
            raw = response.read(_MAX_RESPONSE_BYTES + 1)
            if len(raw) > _MAX_RESPONSE_BYTES:
                return {**response_base, "ok": False, "http_status": status,
                        "reason": "mcp_probe_response_too_large"}
            try:
                payload = json.loads(raw)
            except (ValueError, UnicodeDecodeError):
                return {**response_base, "ok": False, "http_status": status,
                        "reason": "mcp_invalid_response_json"}
            result = payload.get("result") if isinstance(payload, dict) else None
            matched = (
                isinstance(payload, dict)
                and payload.get("jsonrpc") == "2.0"
                and payload.get("id") == 1
                and isinstance(result, dict)
                and isinstance(result.get("capabilities"), dict)
            )
            if modern:
                matched = (
                    matched
                    and isinstance(result, dict)
                    and result.get("resultType") == "complete"
                    and isinstance(result.get("supportedVersions"), list)
                    and MODERN_PROTOCOL_VERSION in result["supportedVersions"]
                )
            return {
                **response_base, "ok": bool(matched), "http_status": status,
                "mcp_discovery_verified": bool(matched) if modern else False,
                "mcp_initialize_verified": bool(matched) if not modern else False,
                "reason": (
                    "discover_verified_tools_not_checked" if matched and modern
                    else "initialize_response_verified_tools_not_checked" if matched
                    else "mcp_discovery_response_not_modern" if modern
                    else "mcp_initialize_response_not_mcp"
                ),
            }
    except urllib.error.HTTPError as exc:
        code = int(exc.code)
        if 300 <= code < 400:
            return {**response_base, "ok": False, "http_status": code,
                    "reason": "mcp_http_redirect_rejected"}
        try:
            error_payload = json.loads(exc.read(_MAX_RESPONSE_BYTES + 1))
        except (ValueError, UnicodeDecodeError, OSError):
            error_payload = None
        error = error_payload.get("error") if isinstance(error_payload, dict) else None
        error_code = error.get("code") if isinstance(error, dict) else None
        # Do not downgrade an auth challenge, rate limit, or recognized modern
        # protocol error to legacy initialize. A legacy fallback is at most one
        # additional POST to the exact same validated endpoint.
        fallback = modern and code in {400, 404, 405, 406, 415, 422} and error_code not in {
            -32020, -32022, -32601,
        }
        reasons = {
            401: "mcp_authentication_required",
            403: "mcp_access_forbidden",
            404: "mcp_path_missing_or_wrong_service",
            405: "mcp_post_not_supported",
            429: "mcp_rate_limited",
        }
        return {
            **response_base, "ok": False, "http_status": code,
            "reason": (
                "mcp_modern_protocol_error" if modern and error_code in {-32020, -32022, -32601}
                else reasons.get(code, "mcp_http_error")
            ),
            "_fallback_legacy": fallback,
        }
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return {**response_base, "ok": False,
                "reason": "mcp_transport_unreachable",
                "transport_exception": type(exc).__name__}


def probe_mcp_endpoint(url: str, *, timeout: float = 3.0) -> dict[str, Any]:
    """Probe 2026-07-28 first; inspect legacy initialize only if safely needed.

    A successful HTTP probe never validates tools/list, credentials, a
    ChatGPT app binding, or an accepted Jaźń visible turn.
    """
    try:
        endpoint = validate_probe_url(url)
        if not 0.1 <= float(timeout) <= 30.0:
            raise ValueError("mcp_probe_timeout_out_of_range")
    except (TypeError, ValueError) as exc:
        return {"ok": False, "reason": str(exc),
                "mcp_discovery_verified": False,
                "mcp_initialize_verified": False,
                "toolset_verified": False}

    base: dict[str, Any] = {
        "endpoint": endpoint,
        "mcp_discovery_verified": False,
        "mcp_initialize_verified": False,
        "toolset_verified": False,
        "chatgpt_tools_exposed": None,
        "accepted_visible_turn": False,
    }
    modern = _round_trip(endpoint, base, modern=True, timeout=float(timeout))
    if modern.pop("_fallback_legacy", False):
        legacy = _round_trip(endpoint, base, modern=False, timeout=float(timeout))
        legacy.pop("_fallback_legacy", None)
        legacy["legacy_fallback_used"] = True
        return legacy
    modern["legacy_fallback_used"] = False
    return modern
