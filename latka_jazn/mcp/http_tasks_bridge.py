from __future__ import annotations

"""Bridge the MCP 2026-07-28 Tasks extension over official Streamable HTTP.

The pinned MCP Python SDK v2.2.0 implements the 2026-07-28 core transport and
extension advertisement, but its release notes explicitly list SEP-2663 Tasks
as a known gap.  This adapter intercepts only the extension wire surface that
the SDK cannot currently dispatch:

* task-capable `tools/call` for `jazn_generate_visible_reply`;
* `tasks/get`, `tasks/update`, and `tasks/cancel`.

Every other request remains owned by the official SDK ASGI app.  The bridge
reuses the SDK's bearer verifier and transport-security checker, validates the
2026 standard HTTP routing headers, then delegates to the canonical
`JaznMcpServer`.  It never owns Jaźń runtime semantics or finalization.
"""

import base64
import binascii
import json
from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from pydantic import AnyHttpUrl
from starlette.requests import HTTPConnection, Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp, Receive, Scope, Send

from mcp.server.auth.middleware.bearer_auth import BearerAuthBackend
from mcp.server.auth.provider import TokenVerifier
from mcp.server.transport_security import (
    TransportSecurityMiddleware,
    TransportSecuritySettings,
)

from latka_jazn.mcp.task_resume import TASK_EXTENSION_ID

MCP_PROTOCOL_VERSION = "2026-07-28"
META_PROTOCOL_VERSION = "io.modelcontextprotocol/protocolVersion"
META_CLIENT_CAPABILITIES = "io.modelcontextprotocol/clientCapabilities"
HEADER_MISMATCH = -32020
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603

_TASK_METHODS = frozenset({"tasks/get", "tasks/update", "tasks/cancel"})
_BASE64_PREFIX = "=?base64?"
_BASE64_SUFFIX = "?="


class ModernProtocolBackend(Protocol):
    def handle(self, request_value: dict[str, Any]) -> dict[str, Any] | None: ...


@dataclass(frozen=True, slots=True)
class _Principal:
    subject: str
    scopes: frozenset[str]


def _jsonrpc_error(
    request_id: Any,
    *,
    code: int,
    message: str,
    data: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    error: dict[str, Any] = {"code": int(code), "message": str(message)}
    if data is not None:
        error["data"] = dict(data)
    return {"jsonrpc": "2.0", "id": request_id, "error": error}


def _header_value(value: str) -> str:
    if value.startswith(_BASE64_PREFIX) and value.endswith(_BASE64_SUFFIX):
        encoded = value[len(_BASE64_PREFIX) : -len(_BASE64_SUFFIX)]
        try:
            decoded = base64.b64decode(encoded, validate=True)
            return decoded.decode("utf-8")
        except (binascii.Error, UnicodeDecodeError) as exc:
            raise ValueError("invalid_base64_header_value") from exc
    return value


def _client_supports_tasks(request_value: Mapping[str, Any]) -> bool:
    params = request_value.get("params")
    if not isinstance(params, Mapping):
        return False
    metadata = params.get("_meta")
    if not isinstance(metadata, Mapping):
        return False
    capabilities = metadata.get(META_CLIENT_CAPABILITIES)
    if not isinstance(capabilities, Mapping):
        return False
    extensions = capabilities.get("extensions")
    return isinstance(extensions, Mapping) and TASK_EXTENSION_ID in extensions


def _task_intercept_candidate(request_value: Mapping[str, Any]) -> bool:
    method = str(request_value.get("method") or "")
    if method in _TASK_METHODS:
        return True
    if method != "tools/call" or not _client_supports_tasks(request_value):
        return False
    params = request_value.get("params")
    return (
        isinstance(params, Mapping)
        and str(params.get("name") or "") == "jazn_generate_visible_reply"
    )


def _expected_mcp_name(request_value: Mapping[str, Any]) -> str | None:
    method = str(request_value.get("method") or "")
    params = request_value.get("params")
    if not isinstance(params, Mapping):
        return None
    if method == "tools/call":
        return str(params.get("name") or "")
    if method in _TASK_METHODS:
        return str(params.get("taskId") or "")
    return None


class ModernTasksHttpBridge:
    """Narrow ASGI interceptor for the Tasks extension missing from SDK v2.2.0."""

    @property
    def routes(self) -> Any:
        """Expose wrapped Starlette routes for diagnostics without owning routing."""

        return getattr(self.app, "routes", ())

    def __init__(
        self,
        app: ASGIApp,
        *,
        protocol_backend: ModernProtocolBackend,
        internal_token: str,
        token_verifier: TokenVerifier | None,
        resource_server_url: str | None,
        allow_unauthenticated_loopback_dev: bool,
        transport_security: TransportSecuritySettings,
        max_request_body_size: int,
        required_base_scopes: tuple[str, ...],
        operation_scopes: Mapping[str, str],
        public_tool_names: frozenset[str],
    ) -> None:
        self.app = app
        self.protocol_backend = protocol_backend
        self.internal_token = str(internal_token)
        self.token_verifier = token_verifier
        self.resource_server_url = str(resource_server_url or "").strip() or None
        self.allow_unauthenticated_loopback_dev = bool(
            allow_unauthenticated_loopback_dev
        )
        self.security = TransportSecurityMiddleware(transport_security)
        self.max_request_body_size = int(max_request_body_size)
        self.required_base_scopes = tuple(str(item) for item in required_base_scopes)
        self.operation_scopes = {
            str(key): str(value) for key, value in operation_scopes.items()
        }
        self.public_tool_names = frozenset(str(item) for item in public_tool_names)

    async def _principal(self, scope: Scope) -> _Principal | None:
        if self.token_verifier is None:
            if not self.allow_unauthenticated_loopback_dev:
                return None
            return _Principal(
                subject="loopback-development",
                scopes=frozenset(
                    set(self.required_base_scopes)
                    | set(self.operation_scopes.values())
                ),
            )

        resource = (
            AnyHttpUrl(self.resource_server_url)
            if self.resource_server_url is not None
            else None
        )
        auth_backend = BearerAuthBackend(
            self.token_verifier,
            resource_server_url=resource,
        )
        authenticated = await auth_backend.authenticate(HTTPConnection(scope))
        if authenticated is None:
            return None
        credentials, user = authenticated
        access_token = getattr(user, "access_token", None)
        if access_token is None:
            return None
        subject = str(
            getattr(access_token, "subject", None)
            or getattr(access_token, "client_id", None)
            or "oauth-client"
        ).strip() or "oauth-client"
        return _Principal(
            subject=subject,
            scopes=frozenset(str(item) for item in credentials.scopes),
        )

    @staticmethod
    def _operation_key(request_value: Mapping[str, Any]) -> str:
        method = str(request_value.get("method") or "")
        if method != "tools/call":
            return method
        params = request_value.get("params")
        return str(params.get("name") or "") if isinstance(params, Mapping) else ""

    def _validate_standard_headers(
        self,
        request: Request,
        request_value: Mapping[str, Any],
    ) -> dict[str, Any] | None:
        request_id = request_value.get("id")
        params = request_value.get("params")
        metadata = params.get("_meta") if isinstance(params, Mapping) else None
        body_version = (
            str(metadata.get(META_PROTOCOL_VERSION) or "")
            if isinstance(metadata, Mapping)
            else ""
        )
        header_version = str(request.headers.get("mcp-protocol-version") or "")
        body_method = str(request_value.get("method") or "")
        header_method = str(request.headers.get("mcp-method") or "")

        if not header_version or header_version != body_version:
            return _jsonrpc_error(
                request_id,
                code=HEADER_MISMATCH,
                message="Header mismatch: MCP-Protocol-Version does not match request metadata",
            )
        if not header_method or header_method != body_method:
            return _jsonrpc_error(
                request_id,
                code=HEADER_MISMATCH,
                message="Header mismatch: Mcp-Method does not match request method",
            )

        expected_name = _expected_mcp_name(request_value)
        if expected_name is not None:
            raw_name = request.headers.get("mcp-name")
            if raw_name is None:
                return _jsonrpc_error(
                    request_id,
                    code=HEADER_MISMATCH,
                    message="Header mismatch: required Mcp-Name header is missing",
                )
            try:
                decoded_name = _header_value(str(raw_name))
            except ValueError:
                return _jsonrpc_error(
                    request_id,
                    code=HEADER_MISMATCH,
                    message="Header mismatch: Mcp-Name header encoding is invalid",
                )
            if decoded_name != expected_name:
                return _jsonrpc_error(
                    request_id,
                    code=HEADER_MISMATCH,
                    message="Header mismatch: Mcp-Name does not match request body",
                )
        return None

    async def _send_json(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
        payload: Mapping[str, Any],
        *,
        status_code: int = 200,
    ) -> None:
        response = JSONResponse(
            dict(payload),
            status_code=status_code,
            headers={"MCP-Protocol-Version": MCP_PROTOCOL_VERSION},
        )
        await response(scope, receive, send)

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        if (
            scope.get("type") != "http"
            or str(scope.get("method") or "").upper() != "POST"
            or str(scope.get("path") or "") != "/mcp"
        ):
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive=receive)
        protocol_header = str(request.headers.get("mcp-protocol-version") or "")
        if protocol_header != MCP_PROTOCOL_VERSION:
            await self.app(scope, receive, send)
            return

        security_error = await self.security.validate_request(request, is_post=True)
        if security_error is not None:
            await security_error(scope, receive, send)
            return

        content_length = request.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > self.max_request_body_size:
                    await Response("Request body too large", status_code=413)(
                        scope, receive, send
                    )
                    return
            except ValueError:
                pass

        body = await request.body()
        if len(body) > self.max_request_body_size:
            await Response("Request body too large", status_code=413)(
                scope, receive, send
            )
            return
        try:
            request_value = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            await self._send_json(
                scope,
                receive,
                send,
                _jsonrpc_error(None, code=-32700, message="Parse error"),
                status_code=400,
            )
            return
        if not isinstance(request_value, dict):
            await self._send_json(
                scope,
                receive,
                send,
                _jsonrpc_error(None, code=INVALID_PARAMS, message="Request must be an object"),
                status_code=400,
            )
            return

        if not _task_intercept_candidate(request_value):
            replayed = False

            async def replay_receive():
                nonlocal replayed
                if not replayed:
                    replayed = True
                    return {"type": "http.request", "body": body, "more_body": False}
                return {"type": "http.disconnect"}

            await self.app(scope, replay_receive, send)
            return

        header_error = self._validate_standard_headers(request, request_value)
        if header_error is not None:
            await self._send_json(
                scope,
                receive,
                send,
                header_error,
                status_code=400,
            )
            return

        principal = await self._principal(scope)
        if principal is None:
            await Response(
                json.dumps(
                    {
                        "error": "invalid_token",
                        "error_description": "Authentication required",
                    }
                ),
                status_code=401,
                media_type="application/json",
                headers={"WWW-Authenticate": "Bearer"},
            )(scope, receive, send)
            return

        missing_base = [
            scope_name
            for scope_name in self.required_base_scopes
            if scope_name not in principal.scopes
        ]
        operation = self._operation_key(request_value)
        operation_scope = self.operation_scopes.get(operation)
        if operation_scope is None:
            await self._send_json(
                scope,
                receive,
                send,
                _jsonrpc_error(
                    request_value.get("id"),
                    code=INVALID_PARAMS,
                    message="Operation is not exposed by the public MCP ingress",
                ),
            )
            return
        if missing_base or operation_scope not in principal.scopes:
            await Response(
                json.dumps(
                    {
                        "error": "insufficient_scope",
                        "error_description": "Required MCP scope is missing",
                    }
                ),
                status_code=403,
                media_type="application/json",
                headers={"WWW-Authenticate": "Bearer error=\"insufficient_scope\""},
            )(scope, receive, send)
            return

        if operation == "jazn_generate_visible_reply":
            params = request_value.get("params")
            tool_name = str(params.get("name") or "") if isinstance(params, Mapping) else ""
            if tool_name not in self.public_tool_names:
                await self._send_json(
                    scope,
                    receive,
                    send,
                    _jsonrpc_error(
                        request_value.get("id"),
                        code=INVALID_PARAMS,
                        message="Unknown public tool",
                    ),
                )
                return

        prepared = dict(request_value)
        prepared_params = dict(prepared.get("params") or {})
        prepared_meta = dict(prepared_params.get("_meta") or {})
        prepared_meta.update(
            {
                "authorization": self.internal_token,
                "subject": principal.subject,
                "openai/subject": principal.subject,
            }
        )
        prepared_params["_meta"] = prepared_meta
        prepared["params"] = prepared_params

        try:
            response_value = self.protocol_backend.handle(prepared)
        except Exception:
            response_value = _jsonrpc_error(
                prepared.get("id"),
                code=INTERNAL_ERROR,
                message="Internal MCP task bridge error",
            )
        if response_value is None:
            await Response(status_code=202)(scope, receive, send)
            return
        await self._send_json(scope, receive, send, response_value)


__all__ = [
    "MCP_PROTOCOL_VERSION",
    "ModernProtocolBackend",
    "ModernTasksHttpBridge",
]
