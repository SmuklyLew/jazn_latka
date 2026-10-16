from __future__ import annotations

"""Read-only MCP tools/list verification for the Jaźń ChatGPT bridge.

This checks a real endpoint catalog, not ChatGPT host registration, daemon
liveness, or accepted turns. Never submits a conversation message.
"""

import json
import os
from typing import Any, Mapping
import urllib.error
import urllib.request
from urllib.parse import urlsplit

from latka_jazn.mcp.chatgpt_toolset import REQUIRED_CHATGPT_TURN_TOOLS
from latka_jazn.mcp.ingress_diagnostics import (
    MODERN_PROTOCOL_VERSION,
    _RejectRedirects,
    validate_probe_url,
)

_MAX_BYTES = 262144
_MAX_PAGES = 8


def _report(
    reason: str, *, observed: set[str] | None = None,
    metadata_ok: bool = False, pages: int = 0,
) -> dict[str, Any]:
    names = set() if observed is None else observed
    missing = [name for name in REQUIRED_CHATGPT_TURN_TOOLS if name not in names]
    complete = reason == "mcp_chatgpt_tool_catalog_verified" and not missing and metadata_ok
    return {
        "schema_version": "jazn_chatgpt_mcp_tool_catalog_probe/v1",
        "ok": complete,
        "reason": reason,
        "protocol_version": MODERN_PROTOCOL_VERSION,
        "tool_catalog_verified": complete,
        "required_tool_names": list(REQUIRED_CHATGPT_TURN_TOOLS),
        "missing_required_tool_names": missing,
        "metadata_verified": metadata_ok and complete,
        "pages_checked": pages,
        "chatgpt_current_message_toolset_verified": False,
        "daemon_conversation_ready_verified": False,
        "accepted_visible_turn_verified": False,
        "truth_boundary": (
            "Only an MCP endpoint tool catalog was inspected. It does not prove "
            "the current ChatGPT message exposes the tools, the daemon is ready, "
            "or a visible turn has been accepted."
        ),
    }


def _required_tool_metadata_problem(
    tool: Mapping[str, Any], *, require_oauth: bool,
) -> str | None:
    """Check the model-callable MCP descriptor, not just its name.

    Fail closed on hidden tools, missing safety annotations or a remote
    endpoint that advertises no authenticated access. None of this is
    current-message ChatGPT tool exposure or proof of a live daemon.
    """
    description = tool.get("description")
    input_schema = tool.get("inputSchema")
    if (
        not isinstance(description, str) or not description.strip()
        or not isinstance(input_schema, dict)
        or input_schema.get("type") != "object"
    ):
        return "mcp_chatgpt_tool_metadata_invalid"

    meta = tool.get("_meta")
    ui = meta.get("ui") if isinstance(meta, dict) else None
    visibility = ui.get("visibility") if isinstance(ui, dict) else None
    if (
        not isinstance(visibility, list)
        or len(visibility) != 2
        or set(map(str, visibility)) != {"model", "app"}
    ):
        return "mcp_chatgpt_tool_visibility_invalid"

    annotations = tool.get("annotations")
    read_only = tool["name"] in {"jazn_status", "jazn_resume_visible_reply"}
    if (
        not isinstance(annotations, dict)
        or annotations.get("readOnlyHint") is not read_only
        or annotations.get("destructiveHint") is not False
        or annotations.get("openWorldHint") is not False
        or annotations.get("idempotentHint") is not True
    ):
        return "mcp_chatgpt_tool_annotations_invalid"

    schemes = tool.get("securitySchemes")
    if schemes is None and isinstance(meta, dict):
        schemes = meta.get("securitySchemes")
    if not isinstance(schemes, list) or not schemes:
        return "mcp_chatgpt_tool_security_invalid"
    supported = False
    for scheme in schemes:
        if not isinstance(scheme, dict):
            return "mcp_chatgpt_tool_security_invalid"
        scheme_type = scheme.get("type")
        if scheme_type == "oauth2":
            scopes = scheme.get("scopes")
            if not isinstance(scopes, list) or not scopes or not all(
                isinstance(scope, str) and scope.strip() for scope in scopes
            ):
                return "mcp_chatgpt_tool_security_invalid"
            supported = True
        elif scheme_type == "noauth" and not require_oauth:
            supported = True
        else:
            return "mcp_chatgpt_tool_security_invalid"
    if not supported:
        return "mcp_chatgpt_tool_security_invalid"
    return None


def probe_chatgpt_mcp_tool_catalog(
    url: str, *, timeout: float = 3.0,
    token_env: str | None = None,
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Inspect tools/list only. Bounded pages, payload size, no redirects or writes.

    OAuth bearer tokens, if used, come from an explicit environment variable.
    Neither token values nor the URL are included in results or errors.
    """
    try:
        endpoint = validate_probe_url(url)
        duration = float(timeout)
        if not 0.1 <= duration <= 30.0:
            raise ValueError("mcp_catalog_timeout_out_of_range")
    except (TypeError, ValueError) as exc:
        return _report(str(exc))

    token: str | None = None
    if token_env is not None:
        if not token_env or not token_env.isidentifier():
            return _report("mcp_catalog_invalid_token_env_name")
        if urlsplit(endpoint).scheme != "https":
            return _report("mcp_catalog_bearer_requires_https")
        value = (os.environ if environ is None else environ).get(token_env, "")
        if not value or value != value.strip() or any(ch in value for ch in "\r\n"):
            return _report("mcp_catalog_token_env_missing_or_invalid")
        token = value

    opener = urllib.request.build_opener(_RejectRedirects())
    names: set[str] = set()
    checks: dict[str, str | None] = {}
    require_oauth = urlsplit(endpoint).scheme == "https"
    cursor: str | None = None
    seen_cursors: set[str] = set()
    for page in range(_MAX_PAGES):
        params: dict[str, Any] = {
            "_meta": {
                "io.modelcontextprotocol/protocolVersion": MODERN_PROTOCOL_VERSION,
                "io.modelcontextprotocol/clientInfo": {
                    "name": "jazn-chatgpt-tool-catalog-probe", "version": "1",
                },
                "io.modelcontextprotocol/clientCapabilities": {},
            }
        }
        if cursor is not None:
            params["cursor"] = cursor
        data = json.dumps({
            "jsonrpc": "2.0", "id": page + 1,
            "method": "tools/list", "params": params,
        }, separators=(",", ":")).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": MODERN_PROTOCOL_VERSION,
            "Mcp-Method": "tools/list",
        }
        if token is not None:
            headers["Authorization"] = "Bearer " + token
        request = urllib.request.Request(
            endpoint, data=data, method="POST", headers=headers,
        )
        try:
            with opener.open(request, timeout=duration) as response:
                if response.status != 200:
                    return _report("mcp_catalog_unexpected_http_status", observed=names, pages=page + 1)
                response_url = response.geturl() if callable(getattr(response, "geturl", None)) else endpoint
                if response_url != endpoint:
                    return _report("mcp_catalog_redirect_rejected", observed=names, pages=page + 1)
                media = str(response.headers.get("Content-Type", "")).lower()
                if "text/event-stream" in media:
                    return _report("mcp_catalog_sse_requires_inspector", observed=names, pages=page + 1)
                if "application/json" not in media:
                    return _report("mcp_catalog_not_json", observed=names, pages=page + 1)
                raw = response.read(_MAX_BYTES + 1)
                if len(raw) > _MAX_BYTES:
                    return _report("mcp_catalog_response_too_large", observed=names, pages=page + 1)
        except urllib.error.HTTPError as exc:
            if 300 <= exc.code < 400:
                reason = "mcp_catalog_redirect_rejected"
            else:
                reason = {
                    401: "mcp_catalog_auth_required",
                    403: "mcp_catalog_forbidden",
                    404: "mcp_catalog_endpoint_missing",
                    429: "mcp_catalog_rate_limited",
                }.get(exc.code, "mcp_catalog_http_error")
            return _report(reason, observed=names, pages=page + 1)
        except (OSError, TimeoutError, urllib.error.URLError):
            return _report("mcp_catalog_unreachable", observed=names, pages=page + 1)
        try:
            payload = json.loads(raw)
        except (ValueError, UnicodeDecodeError):
            return _report("mcp_catalog_invalid_json", observed=names, pages=page + 1)
        if not isinstance(payload, dict) or payload.get("jsonrpc") != "2.0" or payload.get("id") != page + 1:
            return _report("mcp_catalog_invalid_rpc_envelope", observed=names, pages=page + 1)
        result = payload.get("result")
        if not isinstance(result, dict) or result.get("resultType") != "complete":
            return _report("mcp_catalog_incomplete_protocol_result", observed=names, pages=page + 1)
        tools = result.get("tools")
        if not isinstance(tools, list):
            return _report("mcp_catalog_tools_not_array", observed=names, pages=page + 1)
        for tool in tools:
            if not isinstance(tool, dict) or not isinstance(tool.get("name"), str):
                return _report("mcp_catalog_tool_invalid", observed=names, pages=page + 1)
            name = tool["name"]
            if name in names:
                return _report("mcp_catalog_duplicate_tool_name", observed=names, pages=page + 1)
            names.add(name)
            if name in REQUIRED_CHATGPT_TURN_TOOLS:
                checks[name] = _required_tool_metadata_problem(
                    tool, require_oauth=require_oauth,
                )
        next_cursor = result.get("nextCursor")
        if next_cursor is None:
            missing = any(name not in names for name in REQUIRED_CHATGPT_TURN_TOOLS)
            metadata_problem = next(
                (checks.get(name) for name in REQUIRED_CHATGPT_TURN_TOOLS
                 if checks.get(name) is not None),
                None,
            )
            metadata_ok = not missing and metadata_problem is None
            reason = (
                "mcp_chatgpt_required_tools_missing" if missing
                else metadata_problem if metadata_problem is not None
                else "mcp_chatgpt_tool_catalog_verified"
            )
            return _report(reason, observed=names, metadata_ok=metadata_ok, pages=page + 1)
        if not isinstance(next_cursor, str) or not next_cursor or len(next_cursor) > 512:
            return _report("mcp_catalog_cursor_invalid", observed=names, pages=page + 1)
        if next_cursor in seen_cursors:
            return _report("mcp_catalog_cursor_cycle", observed=names, pages=page + 1)
        seen_cursors.add(next_cursor)
        cursor = next_cursor
    return _report("mcp_catalog_page_limit", observed=names, pages=_MAX_PAGES)


__all__ = ["probe_chatgpt_mcp_tool_catalog"]
