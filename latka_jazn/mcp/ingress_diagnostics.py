from __future__ import annotations

"""Read-only, fail-closed probe of a configured Jaźń Streamable HTTP MCP URL.

The probe does not register an app, authenticate, submit a user turn or claim
that ChatGPT exposed any tools. Its initialize request carries no user data.
"""

import json
from typing import Any
import urllib.error
import urllib.request
from urllib.parse import urlsplit


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


def probe_mcp_endpoint(url: str, *, timeout: float = 3.0) -> dict[str, Any]:
    """Check MCP initialize without sending credentials or user messages.

    HTTP success alone never proves model tool exposure or an accepted turn.
    SSE responses are marked as needing an inspector instead of being mistaken
    for a JSON RPC reply.
    """
    try:
        endpoint = validate_probe_url(url)
        if not 0.1 <= float(timeout) <= 30.0:
            raise ValueError("mcp_probe_timeout_out_of_range")
    except (TypeError, ValueError) as exc:
        return {"ok": False, "reason": str(exc), "mcp_initialize_verified": False,
                "toolset_verified": False}

    base: dict[str, Any] = {
        "endpoint": endpoint,
        "mcp_initialize_verified": False,
        "toolset_verified": False,
        "chatgpt_tools_exposed": None,
        "accepted_visible_turn": False,
    }
    request_body = json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {
            "protocolVersion": "2026-07-28",
            "capabilities": {},
            "clientInfo": {"name": "jazn-mcp-preflight", "version": "1"},
        },
    }).encode("utf-8")
    request = urllib.request.Request(
        endpoint, data=request_body, method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=float(timeout)) as response:
            status = int(response.status)
            media = str(response.headers.get("Content-Type", "")).lower()
            if status != 200:
                return {**base, "ok": False, "http_status": status,
                        "reason": "mcp_initialize_http_unexpected_status"}
            if "text/event-stream" in media:
                return {**base, "ok": False, "http_status": status,
                        "reason": "mcp_sse_requires_protocol_inspector"}
            if "application/json" not in media:
                return {**base, "ok": False, "http_status": status,
                        "reason": "mcp_unexpected_content_type"}
            raw = response.read(65537)
            if len(raw) > 65536:
                return {**base, "ok": False, "http_status": status,
                        "reason": "mcp_initialize_response_too_large"}
            try:
                payload = json.loads(raw)
            except (ValueError, UnicodeDecodeError):
                return {**base, "ok": False, "http_status": status,
                        "reason": "mcp_invalid_initialize_json"}
            verified = (
                isinstance(payload, dict)
                and payload.get("jsonrpc") == "2.0"
                and payload.get("id") == 1
                and isinstance(payload.get("result"), dict)
                and isinstance(payload["result"].get("capabilities"), dict)
            )
            return {**base, "ok": bool(verified), "http_status": status,
                    "mcp_initialize_verified": bool(verified),
                    "reason": ("initialize_verified_tools_not_checked" if verified
                               else "mcp_initialize_response_not_mcp")}
    except urllib.error.HTTPError as exc:
        code = int(exc.code)
        reason = {
            401: "mcp_authentication_required",
            403: "mcp_access_forbidden",
            404: "mcp_path_missing_or_wrong_service",
            405: "mcp_post_not_supported",
        }.get(code, "mcp_http_error")
        return {**base, "ok": False, "http_status": code, "reason": reason}
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return {**base, "ok": False,
                "reason": "mcp_transport_unreachable",
                "transport_exception": type(exc).__name__}
