from __future__ import annotations

"""Official MCP Python SDK v2 Streamable HTTP ingress for the persistent Jaźń runtime.

This module is intentionally an adapter. It does not own conversation semantics,
memory, finalization, daemon lifecycle, or operation identity. Those stay in the
existing Jaźń runtime and :class:`JaznMcpServer`. The public HTTP surface exposes
only the four tools required for a visible turn and keeps the audit tool private.

Production HTTP is fail-closed: callers must provide an SDK ``TokenVerifier`` and
OAuth resource-server settings. An unauthenticated mode exists only for explicit
loopback development/tests. The private daemon remains bound behind
``SecureHostRuntimeGateway`` and is never exposed directly.
"""

from collections import defaultdict, deque
from dataclasses import dataclass
import ipaddress
from pathlib import Path
import secrets
import threading
import time
from typing import Annotated, Any, Mapping, Protocol

from pydantic import AnyHttpUrl, Field
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from mcp.server import MCPServer
from mcp.server.extension import Extension
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import TokenVerifier
from mcp.server.auth.settings import AuthSettings
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import CallToolResult, ContentBlock, TextContent, ToolAnnotations

from latka_jazn.core.runtime_root import find_runtime_root
from latka_jazn.mcp.http_tasks_bridge import ModernTasksHttpBridge
from latka_jazn.mcp.server import JaznMcpServer, TASK_EXTENSION_ID
from latka_jazn.mcp.task_resume import McpTaskStore
from latka_jazn.version import PACKAGE_VERSION_FULL

MCP_PROTOCOL_VERSION = "2026-07-28"
MCP_PATH = "/mcp"
HEALTH_PATH = "/healthz"
READINESS_PATH = "/readyz"
DEFAULT_MAX_REQUEST_BYTES = 1 * 1024 * 1024

SCOPE_CONNECT = "jazn:mcp:connect"
SCOPE_TURN_SUBMIT = "jazn:turn:submit"
SCOPE_TURN_READ = "jazn:turn:read"
SCOPE_TURN_FINALIZE = "jazn:turn:finalize"
SCOPE_STATUS_READ = "jazn:status:read"
SCOPE_TASK_READ = "jazn:task:read"
SCOPE_TASK_UPDATE = "jazn:task:update"
SCOPE_TASK_CANCEL = "jazn:task:cancel"

_PUBLIC_TOOLS = frozenset(
    {
        "jazn_generate_visible_reply",
        "jazn_resume_visible_reply",
        "jazn_finalize_reply",
        "jazn_status",
    }
)

_TOOL_SCOPES = {
    "jazn_generate_visible_reply": SCOPE_TURN_SUBMIT,
    "jazn_resume_visible_reply": SCOPE_TURN_READ,
    "jazn_finalize_reply": SCOPE_TURN_FINALIZE,
    "jazn_status": SCOPE_STATUS_READ,
}

_TOOL_RATE_LIMITS_PER_MINUTE = {
    "jazn_generate_visible_reply": 10,
    "jazn_finalize_reply": 30,
    "jazn_resume_visible_reply": 120,
    "jazn_status": 120,
}

RequestId = Annotated[str, Field(min_length=1, max_length=256)]
SessionId = Annotated[str | None, Field(max_length=128)]
MessageText = Annotated[str, Field(min_length=1, max_length=262_144)]
ContinuationToken = Annotated[str, Field(min_length=1, max_length=4096)]
FinalText = Annotated[str, Field(max_length=524_288)]
Sha256Hex = Annotated[str, Field(pattern=r"^[0-9a-fA-F]{64}$")]


class PublicIngressBackend(Protocol):
    def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
        *,
        meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]: ...


class ModernProtocolBackend(Protocol):
    def handle(self, request_value: dict[str, Any]) -> dict[str, Any] | None: ...


class _TasksCapabilityExtension(Extension):
    """Advertise the official Tasks extension while Jaźń owns its durable store."""

    identifier = TASK_EXTENSION_ID


@dataclass(frozen=True, slots=True)
class PublicMcpGatewayConfig:
    root: Path
    daemon_url: str = "http://127.0.0.1:8787"
    host: str = "127.0.0.1"
    port: int = 8080
    streamable_http_path: str = MCP_PATH
    max_request_body_size: int = DEFAULT_MAX_REQUEST_BYTES
    allow_unauthenticated_loopback_dev: bool = False
    oauth_issuer_url: str | None = None
    oauth_resource_server_url: str | None = None
    oauth_required_scopes: tuple[str, ...] = (SCOPE_CONNECT,)
    allowed_hosts: tuple[str, ...] = ()
    allowed_origins: tuple[str, ...] = ()

    @property
    def loopback_host(self) -> bool:
        if self.host == "localhost":
            return True
        try:
            return ipaddress.ip_address(self.host).is_loopback
        except ValueError:
            return False

    def validate(self, *, token_verifier_configured: bool) -> None:
        if self.streamable_http_path != MCP_PATH:
            raise ValueError("public_mcp_path_must_be_/mcp")
        if self.port < 1 or self.port > 65535:
            raise ValueError("public_mcp_port_out_of_range")
        if self.max_request_body_size < 1024 or self.max_request_body_size > 4 * 1024 * 1024:
            raise ValueError("public_mcp_request_body_limit_out_of_range")
        if not self.daemon_url.startswith(("http://127.0.0.1:", "http://localhost:", "http://[::1]:")):
            raise ValueError("public_mcp_daemon_must_remain_loopback")

        if token_verifier_configured:
            if not self.oauth_issuer_url or not self.oauth_resource_server_url:
                raise ValueError("oauth_issuer_and_resource_server_urls_required")
        else:
            if not (self.loopback_host and self.allow_unauthenticated_loopback_dev):
                raise ValueError("oauth_token_verifier_required_outside_explicit_loopback_dev")

        if not self.loopback_host and not self.allowed_hosts:
            raise ValueError("public_mcp_allowed_hosts_required_for_non_loopback_bind")


class _PublicRateLimiter:
    def __init__(self) -> None:
        self._events: dict[tuple[str, str], deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, *, subject: str, tool_name: str) -> bool:
        limit = int(_TOOL_RATE_LIMITS_PER_MINUTE[tool_name])
        now = time.monotonic()
        key = (subject, tool_name)
        with self._lock:
            queue = self._events[key]
            while queue and now - queue[0] >= 60.0:
                queue.popleft()
            if len(queue) >= limit:
                return False
            queue.append(now)
        return True


@dataclass(frozen=True, slots=True)
class _Principal:
    subject: str
    scopes: frozenset[str]


def _text_blocks(value: Mapping[str, Any]) -> list[ContentBlock]:
    result: list[ContentBlock] = []
    raw_content = value.get("content")
    if isinstance(raw_content, list):
        for item in raw_content:
            if isinstance(item, Mapping) and str(item.get("type") or "") == "text":
                result.append(TextContent(type="text", text=str(item.get("text") or "")))
    if not result:
        result.append(TextContent(type="text", text="Jaźń runtime returned no textual tool content."))
    return result


def _call_tool_result(value: Mapping[str, Any]) -> CallToolResult:
    structured = value.get("structuredContent")
    meta = value.get("_meta")
    return CallToolResult(
        content=_text_blocks(value),
        structured_content=dict(structured) if isinstance(structured, Mapping) else None,
        _meta=dict(meta) if isinstance(meta, Mapping) else None,
        is_error=bool(value.get("isError")),
    )


def _public_error(reason: str, *, request_id: str | None = None) -> CallToolResult:
    structured: dict[str, Any] = {
        "ok": False,
        "action": "host_diagnostic",
        "reason": reason,
    }
    if request_id:
        structured["request_id"] = request_id
        structured["daemon_request_id"] = request_id
    return CallToolResult(
        content=[TextContent(type="text", text=f"Jaźń MCP ingress rejected the request safely: {reason}.")],
        structured_content=structured,
        is_error=True,
    )


def _runtime_ready(status: Mapping[str, Any]) -> bool:
    capability = status.get("capability_matrix")
    return bool(
        status.get("gateway_ok") is True
        and status.get("daemon_reachable") is True
        and isinstance(capability, Mapping)
        and capability.get("conversation_ready") is True
    )


class PublicMcpGateway:
    def __init__(
        self,
        config: PublicMcpGatewayConfig,
        *,
        token_verifier: TokenVerifier | None = None,
        backend: PublicIngressBackend | None = None,
        protocol_backend: ModernProtocolBackend | None = None,
    ) -> None:
        config.validate(token_verifier_configured=token_verifier is not None)
        self.config = config
        self._rate_limiter = _PublicRateLimiter()
        self._internal_token = secrets.token_urlsafe(48)
        if backend is None:
            private_server = JaznMcpServer(
                root=config.root,
                daemon_url=config.daemon_url,
                token=self._internal_token,
            )
            self._backend: PublicIngressBackend = private_server
            self._protocol_backend: ModernProtocolBackend | None = private_server
        else:
            self._backend = backend
            self._protocol_backend = protocol_backend
        self._token_verifier = token_verifier

        auth = None
        if token_verifier is not None:
            auth = AuthSettings(
                issuer_url=AnyHttpUrl(str(config.oauth_issuer_url)),
                resource_server_url=AnyHttpUrl(str(config.oauth_resource_server_url)),
                required_scopes=list(config.oauth_required_scopes),
                validate_token_resource=True,
            )

        self.mcp = MCPServer(
            "jazn-runtime",
            title="Jaźń persistent runtime",
            description=(
                "Authenticated ingress to one persistent Jaźń runtime. The gateway is a client adapter; "
                "it does not own runtime lifecycle, memory or finalization."
            ),
            instructions=(
                "Use jazn_generate_visible_reply exactly once for each new user turn with a stable request_id. "
                "If action=poll_runtime, call jazn_resume_visible_reply for that same request and never replay "
                "the user's message. If action=generate_then_finalize, follow only the returned host contract "
                "and finish with jazn_finalize_reply. Display Jaźń text only for action=display_exact. Never "
                "claim Jaźń is running unless readiness is positively verified."
            ),
            version=PACKAGE_VERSION_FULL,
            token_verifier=token_verifier,
            auth=auth,
            extensions=(
                [_TasksCapabilityExtension()]
                if self._protocol_backend is not None
                else None
            ),
        )
        self._register_tools()
        self._register_resources()
        self._register_routes()

    def _principal(self) -> _Principal | None:
        token = get_access_token()
        if token is None:
            if self.config.loopback_host and self.config.allow_unauthenticated_loopback_dev:
                return _Principal(
                    subject="loopback-development",
                    scopes=frozenset(_TOOL_SCOPES.values())
                    | {
                        SCOPE_CONNECT,
                        SCOPE_TASK_READ,
                        SCOPE_TASK_UPDATE,
                        SCOPE_TASK_CANCEL,
                    },
                )
            return None
        subject = str(token.subject or token.client_id or "oauth-client").strip() or "oauth-client"
        return _Principal(subject=subject, scopes=frozenset(str(scope) for scope in token.scopes))

    def _invoke(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        *,
        request_id: str | None = None,
    ) -> CallToolResult:
        if tool_name not in _PUBLIC_TOOLS:
            return _public_error("tool_not_publicly_exposed", request_id=request_id)
        principal = self._principal()
        if principal is None:
            return _public_error("authenticated_principal_required", request_id=request_id)
        required_scope = _TOOL_SCOPES[tool_name]
        if required_scope not in principal.scopes:
            return _public_error("insufficient_scope", request_id=request_id)
        if not self._rate_limiter.allow(subject=principal.subject, tool_name=tool_name):
            return _public_error("rate_limit_exceeded", request_id=request_id)

        value = self._backend.call_tool(
            tool_name,
            dict(arguments),
            meta={
                "authorization": self._internal_token,
                "subject": principal.subject,
                "openai/subject": principal.subject,
            },
        )
        if not isinstance(value, Mapping):
            return _public_error("backend_result_not_object", request_id=request_id)
        return _call_tool_result(value)

    def _status_snapshot(self) -> dict[str, Any]:
        value = self._backend.call_tool(
            "jazn_status",
            {},
            meta={
                "authorization": self._internal_token,
                "subject": "gateway-readiness",
                "openai/subject": "gateway-readiness",
            },
        )
        structured = value.get("structuredContent") if isinstance(value, Mapping) else None
        return dict(structured) if isinstance(structured, Mapping) else {}

    def _register_tools(self) -> None:
        mutating_idempotent = ToolAnnotations(
            read_only_hint=False,
            destructive_hint=False,
            idempotent_hint=True,
            open_world_hint=False,
        )
        read_only_idempotent = ToolAnnotations(
            read_only_hint=True,
            destructive_hint=False,
            idempotent_hint=True,
            open_world_hint=False,
        )

        @self.mcp.tool(
            name="jazn_generate_visible_reply",
            title="Submit one Jaźń turn",
            description=(
                "Submit exactly one new user turn to the persistent Jaźń runtime. "
                "A stable request_id is mandatory; never replay the user message after an ambiguous transport outcome."
            ),
            annotations=mutating_idempotent,
        )
        def jazn_generate_visible_reply(
            request_id: RequestId,
            message: MessageText,
            session_id: SessionId = None,
        ) -> CallToolResult:
            args: dict[str, Any] = {"request_id": request_id, "message": message}
            if session_id:
                args["session_id"] = session_id
            return self._invoke(
                "jazn_generate_visible_reply",
                args,
                request_id=request_id,
            )

        @self.mcp.tool(
            name="jazn_resume_visible_reply",
            title="Resume one Jaźń turn",
            description=(
                "Read/resume the already submitted daemon request. Use the same daemon_request_id; "
                "this tool never authorizes replaying the original user message."
            ),
            annotations=read_only_idempotent,
        )
        def jazn_resume_visible_reply(daemon_request_id: RequestId) -> CallToolResult:
            return self._invoke(
                "jazn_resume_visible_reply",
                {"daemon_request_id": daemon_request_id},
                request_id=daemon_request_id,
            )

        @self.mcp.tool(
            name="jazn_finalize_reply",
            title="Finalize one Jaźń turn",
            description=(
                "Finalize the host-generated text only against the continuation token and SHA-256 contract "
                "returned by the same Jaźń turn."
            ),
            annotations=mutating_idempotent,
        )
        def jazn_finalize_reply(
            continuation_token: ContinuationToken,
            final_visible_text: FinalText,
            final_visible_text_sha256: Sha256Hex,
        ) -> CallToolResult:
            return self._invoke(
                "jazn_finalize_reply",
                {
                    "continuation_token": continuation_token,
                    "final_text": final_visible_text,
                    "final_text_sha256": final_visible_text_sha256.lower(),
                },
            )

        @self.mcp.tool(
            name="jazn_status",
            title="Read Jaźń readiness",
            description="Read a redacted runtime readiness view. Private operator/audit details are not exposed.",
            annotations=read_only_idempotent,
        )
        def jazn_status() -> CallToolResult:
            principal = self._principal()
            if principal is None:
                return _public_error("authenticated_principal_required")
            if SCOPE_STATUS_READ not in principal.scopes:
                return _public_error("insufficient_scope")
            if not self._rate_limiter.allow(subject=principal.subject, tool_name="jazn_status"):
                return _public_error("rate_limit_exceeded")
            status = self._status_snapshot()
            ready = _runtime_ready(status)
            public_status = {
                "ok": ready,
                "ready": ready,
                "gateway_live": True,
                "daemon_reachable": status.get("daemon_reachable") is True,
                "protocol_version": MCP_PROTOCOL_VERSION,
                "package_version": PACKAGE_VERSION_FULL,
                "public_transport": "streamable_http",
            }
            return CallToolResult(
                content=[
                    TextContent(
                        type="text",
                        text="Jaźń persistent runtime is ready." if ready else "Jaźń persistent runtime is not ready.",
                    )
                ],
                structured_content=public_status,
                is_error=not ready,
            )

    def _require_public_scope(self, scope_name: str) -> _Principal:
        principal = self._principal()
        if principal is None:
            raise PermissionError("authenticated_principal_required")
        if scope_name not in principal.scopes:
            raise PermissionError("insufficient_scope")
        return principal

    def _public_runtime_status(self) -> dict[str, Any]:
        self._require_public_scope(SCOPE_STATUS_READ)
        status = self._status_snapshot()
        capability = status.get("capability_matrix")
        capability_map = dict(capability) if isinstance(capability, Mapping) else {}
        return {
            "ready": _runtime_ready(status),
            "ordinary_dialogue_allowed": capability_map.get("ordinary_dialogue_allowed") is True,
            "daemon_reachable": status.get("daemon_reachable") is True,
            "protocol_version": MCP_PROTOCOL_VERSION,
            "package_version": PACKAGE_VERSION_FULL,
            "public_transport": "streamable_http",
        }

    def _public_memory_status(self) -> dict[str, Any]:
        self._require_public_scope(SCOPE_STATUS_READ)
        status = self._status_snapshot()
        capability = status.get("capability_matrix")
        capability_map = dict(capability) if isinstance(capability, Mapping) else {}
        components = capability_map.get("components")
        components_map = dict(components) if isinstance(components, Mapping) else {}
        result: dict[str, Any] = {"package_version": PACKAGE_VERSION_FULL}
        for name in ("persistent_memory", "recall"):
            value = components_map.get(name)
            item = dict(value) if isinstance(value, Mapping) else {}
            result[name] = {
                "status": item.get("status"),
                "available": item.get("available") is True,
                "required_for_dialogue": item.get("required_for_dialogue") is True,
                "reason": item.get("reason"),
            }
        return result

    def _public_task_status(self, task_id: str) -> dict[str, Any]:
        self._require_public_scope(SCOPE_TASK_READ)
        record = McpTaskStore(self.config.root).get(task_id)
        if record is None:
            raise KeyError("unknown_task")
        return {
            "task": record.to_task_result(),
            "lineage": record.lineage(),
        }

    def _register_resources(self) -> None:
        @self.mcp.resource(
            "jazn://runtime/status",
            name="Jaźń runtime status",
            description="Redacted persistent runtime readiness.",
            mime_type="application/json",
        )
        def runtime_status() -> str:
            return json.dumps(
                self._public_runtime_status(),
                ensure_ascii=False,
                sort_keys=True,
            )

        @self.mcp.resource(
            "jazn://memory/status",
            name="Jaźń memory status",
            description="Redacted persistent-memory and recall readiness.",
            mime_type="application/json",
        )
        def memory_status() -> str:
            return json.dumps(
                self._public_memory_status(),
                ensure_ascii=False,
                sort_keys=True,
            )

        @self.mcp.resource(
            "jazn://task/{taskId}",
            name="Jaźń task status",
            description="Read one durable task by its opaque task id.",
            mime_type="application/json",
        )
        def task_status(taskId: str) -> str:
            return json.dumps(
                self._public_task_status(taskId),
                ensure_ascii=False,
                sort_keys=True,
            )

    def _register_routes(self) -> None:
        @self.mcp.custom_route(HEALTH_PATH, methods=["GET"])
        async def healthz(_request: Request) -> Response:
            return JSONResponse(
                {
                    "status": "live",
                    "gateway_live": True,
                    "package_version": PACKAGE_VERSION_FULL,
                }
            )

        @self.mcp.custom_route(READINESS_PATH, methods=["GET"])
        async def readyz(_request: Request) -> Response:
            try:
                status = self._status_snapshot()
                ready = _runtime_ready(status)
            except Exception:
                ready = False
            return JSONResponse(
                {
                    "status": "ready" if ready else "not_ready",
                    "ready": ready,
                },
                status_code=200 if ready else 503,
            )

    def transport_security(self) -> TransportSecuritySettings:
        if self.config.allowed_hosts:
            return TransportSecuritySettings(
                enable_dns_rebinding_protection=True,
                allowed_hosts=list(self.config.allowed_hosts),
                allowed_origins=list(self.config.allowed_origins),
            )
        # Match the official SDK's localhost default explicitly so the Tasks
        # bridge and the SDK core enforce the same DNS-rebinding boundary.
        return TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=["127.0.0.1:*", "localhost:*", "[::1]:*"],
            allowed_origins=[
                "http://127.0.0.1:*",
                "http://localhost:*",
                "http://[::1]:*",
            ],
        )

    def asgi_app(self):
        sdk_app = self.mcp.streamable_http_app(
            host=self.config.host,
            streamable_http_path=self.config.streamable_http_path,
            json_response=True,
            stateless_http=True,
            max_request_body_size=self.config.max_request_body_size,
            transport_security=self.transport_security(),
        )
        if self._protocol_backend is None:
            return sdk_app
        return ModernTasksHttpBridge(
            sdk_app,
            protocol_backend=self._protocol_backend,
            internal_token=self._internal_token,
            token_verifier=self._token_verifier,
            resource_server_url=self.config.oauth_resource_server_url,
            allow_unauthenticated_loopback_dev=(
                self.config.loopback_host
                and self.config.allow_unauthenticated_loopback_dev
            ),
            transport_security=self.transport_security(),
            max_request_body_size=self.config.max_request_body_size,
            required_base_scopes=tuple(self.config.oauth_required_scopes),
            operation_scopes={
                "jazn_generate_visible_reply": SCOPE_TURN_SUBMIT,
                "tasks/get": SCOPE_TASK_READ,
                "tasks/update": SCOPE_TASK_UPDATE,
                "tasks/cancel": SCOPE_TASK_CANCEL,
            },
            public_tool_names=_PUBLIC_TOOLS,
        )

    def run(self) -> None:
        # MCPServer.run() cannot host the Tasks bridge because SDK v2.2.0 does
        # not implement SEP-2663. Use uvicorn over the composed ASGI app.
        import uvicorn

        uvicorn.run(
            self.asgi_app(),
            host=self.config.host,
            port=self.config.port,
            log_level="info",
        )


def build_public_mcp_gateway(
    *,
    root: Path | None = None,
    daemon_url: str = "http://127.0.0.1:8787",
    host: str = "127.0.0.1",
    port: int = 8080,
    token_verifier: TokenVerifier | None = None,
    oauth_issuer_url: str | None = None,
    oauth_resource_server_url: str | None = None,
    oauth_required_scopes: tuple[str, ...] = (SCOPE_CONNECT,),
    allowed_hosts: tuple[str, ...] = (),
    allowed_origins: tuple[str, ...] = (),
    allow_unauthenticated_loopback_dev: bool = False,
    backend: PublicIngressBackend | None = None,
    protocol_backend: ModernProtocolBackend | None = None,
) -> PublicMcpGateway:
    resolved_root = (root or find_runtime_root(Path(__file__))).resolve()
    config = PublicMcpGatewayConfig(
        root=resolved_root,
        daemon_url=daemon_url,
        host=host,
        port=port,
        allow_unauthenticated_loopback_dev=allow_unauthenticated_loopback_dev,
        oauth_issuer_url=oauth_issuer_url,
        oauth_resource_server_url=oauth_resource_server_url,
        oauth_required_scopes=oauth_required_scopes,
        allowed_hosts=allowed_hosts,
        allowed_origins=allowed_origins,
    )
    return PublicMcpGateway(
        config,
        token_verifier=token_verifier,
        backend=backend,
        protocol_backend=protocol_backend,
    )


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Run the Jaźń MCP v2 Streamable HTTP ingress in explicit loopback development mode."
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--daemon-url", default="http://127.0.0.1:8787")
    args = parser.parse_args()

    # The standalone CLI intentionally cannot create an unauthenticated public
    # listener. Production deployments import build_public_mcp_gateway() and
    # inject an OAuth TokenVerifier plus AuthSettings inputs.
    gateway = build_public_mcp_gateway(
        daemon_url=str(args.daemon_url),
        host=str(args.host),
        port=int(args.port),
        allow_unauthenticated_loopback_dev=True,
    )
    if not gateway.config.loopback_host:
        raise SystemExit("standalone_public_mcp_cli_is_loopback_dev_only")
    gateway.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "DEFAULT_MAX_REQUEST_BYTES",
    "HEALTH_PATH",
    "MCP_PATH",
    "MCP_PROTOCOL_VERSION",
    "ModernProtocolBackend",
    "PublicIngressBackend",
    "PublicMcpGateway",
    "PublicMcpGatewayConfig",
    "READINESS_PATH",
    "SCOPE_CONNECT",
    "SCOPE_STATUS_READ",
    "SCOPE_TASK_CANCEL",
    "SCOPE_TASK_READ",
    "SCOPE_TASK_UPDATE",
    "SCOPE_TURN_FINALIZE",
    "SCOPE_TURN_READ",
    "SCOPE_TURN_SUBMIT",
    "build_public_mcp_gateway",
]
