from __future__ import annotations

"""Dual-era MCP facade for the canonical Jaźń runtime.

The byte-exact v76 server remains the implementation owner for tool execution,
authentication, audit, idempotency and host finalization. This module owns MCP
version/era negotiation plus the transport-facing typed turn contract.

MCP 2026-07-28 is stateless at the protocol layer: every request carries its
protocol version and client capabilities in ``params._meta`` and servers expose
``server/discover`` instead of relying on ``initialize``. Older MCP revisions
continue to use the legacy initialize/initialized handshake. Both paths dispatch
to the same Jaźń runtime and tool implementations.
"""

import argparse
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping

from latka_jazn.mcp import server_legacy_v76 as _legacy
from latka_jazn.mcp.server_legacy_v76 import (
    JaznMcpServer as _V76JaznMcpServer,
    READ_ONLY_TOOLS,
    TASK_EXTENSION_ID,
    TOOL_DEFINITIONS,
)
from latka_jazn.mcp.turn_runtime_adapter import McpTurnRuntimeAdapter
from latka_jazn.runtime.turn_runtime import TURN_RUNTIME_CAPABILITY
from latka_jazn.version import PACKAGE_VERSION_FULL

MCP_PROTOCOL_VERSION_MODERN = "2026-07-28"
MCP_PROTOCOL_VERSION_LATEST_LEGACY = "2025-11-25"
MCP_PROTOCOL_VERSION_LEGACY_TASK_EXTENSION = "2025-06-18"
# Compatibility alias retained for callers that imported the old constant.
MCP_PROTOCOL_VERSION_LATEST = MCP_PROTOCOL_VERSION_MODERN
MCP_SUPPORTED_PROTOCOL_VERSIONS = (
    MCP_PROTOCOL_VERSION_MODERN,
    MCP_PROTOCOL_VERSION_LATEST_LEGACY,
    MCP_PROTOCOL_VERSION_LEGACY_TASK_EXTENSION,
)
MCP_SUPPORTED_LEGACY_PROTOCOL_VERSIONS = (
    MCP_PROTOCOL_VERSION_LATEST_LEGACY,
    MCP_PROTOCOL_VERSION_LEGACY_TASK_EXTENSION,
)

META_PROTOCOL_VERSION = "io.modelcontextprotocol/protocolVersion"
META_CLIENT_INFO = "io.modelcontextprotocol/clientInfo"
META_CLIENT_CAPABILITIES = "io.modelcontextprotocol/clientCapabilities"
META_SERVER_INFO = "io.modelcontextprotocol/serverInfo"

UNSUPPORTED_PROTOCOL_VERSION = -32022
INVALID_PARAMS = -32602
METHOD_NOT_FOUND = -32601
MODERN_DISCOVERY_TTL_MS = 5 * 60 * 1000
MODERN_TOOL_LIST_TTL_MS = 5 * 60 * 1000

_TASK_METHODS = frozenset(
    {
        "tasks/get",
        "tasks/update",
        "tasks/cancel",
        # Historical draft/core methods are also rejected on modern MCP.
        "tasks/list",
        "tasks/result",
    }
)


def __getattr__(name: str) -> Any:
    """Preserve runtime compatibility for non-canonical legacy module exports."""

    return getattr(_legacy, name)


class JaznMcpServer(_V76JaznMcpServer):
    """Protocol facade over one canonical Jaźń runtime and tool surface."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        # These fields belong only to the legacy handshake path. Modern 2026
        # requests never read them; their capabilities are validated per request.
        self.negotiated_protocol_version: str | None = None
        self.client_capabilities: dict[str, Any] = {}
        self.client_initialized = False
        self.turn_runtime = McpTurnRuntimeAdapter()

    @staticmethod
    def _server_info() -> dict[str, str]:
        return {
            "name": "jazn-private-mcp",
            "version": PACKAGE_VERSION_FULL,
        }

    @staticmethod
    def _instructions() -> str:
        return (
            "Use jazn_generate_visible_reply exactly once for a new user turn with a stable request_id. "
            "If action=poll_runtime, call jazn_resume_visible_reply with the same daemon_request_id and "
            "never replay the user message. If action=generate_then_finalize, generate only from the "
            "returned host contract and finish with jazn_finalize_reply. Display Jaźń output only when "
            "the returned action is display_exact."
        )

    @staticmethod
    def _negotiate_legacy_protocol_version(requested: Any) -> str:
        """Negotiate only initialize-capable MCP revisions.

        A client that sends ``initialize`` while preferring 2026-07-28 is using
        the legacy negotiation path, so the server counter-offers the newest
        initialize-capable revision instead of pretending the modern era still
        has a handshake.
        """

        candidate = str(requested or "").strip()
        if candidate in MCP_SUPPORTED_LEGACY_PROTOCOL_VERSIONS:
            return candidate
        return MCP_PROTOCOL_VERSION_LATEST_LEGACY

    # Compatibility alias used by existing callers/tests.
    _negotiate_protocol_version = _negotiate_legacy_protocol_version

    def _server_capabilities(self, protocol_version: str | None = None) -> dict[str, Any]:
        resolved = (
            protocol_version
            or self.negotiated_protocol_version
            or MCP_PROTOCOL_VERSION_LATEST_LEGACY
        )
        capabilities: dict[str, Any] = {
            "tools": {"listChanged": False},
            "experimental": {
                TURN_RUNTIME_CAPABILITY: self.turn_runtime.capability_descriptor(),
            },
        }
        # The v76 task adapter is retained only for its original legacy route.
        # We deliberately do NOT advertise io.modelcontextprotocol/tasks for
        # modern MCP 2026-07-28 because that extension has its own current
        # contract and lifecycle which is not yet fully implemented here.
        if resolved == MCP_PROTOCOL_VERSION_LEGACY_TASK_EXTENSION:
            capabilities["extensions"] = {TASK_EXTENSION_ID: {}}
        return capabilities

    @staticmethod
    def _request_meta(request_value: Mapping[str, Any]) -> Mapping[str, Any]:
        params = request_value.get("params")
        if not isinstance(params, Mapping):
            return {}
        metadata = params.get("_meta")
        return metadata if isinstance(metadata, Mapping) else {}

    @classmethod
    def _is_modern_request(cls, request_value: Mapping[str, Any]) -> bool:
        if request_value.get("method") == "server/discover":
            return True
        metadata = cls._request_meta(request_value)
        return META_PROTOCOL_VERSION in metadata

    @staticmethod
    def _jsonrpc_error(
        request_id: Any,
        *,
        code: int,
        message: str,
        data: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        error: dict[str, Any] = {"code": code, "message": message}
        if data is not None:
            error["data"] = dict(data)
        return {"jsonrpc": "2.0", "id": request_id, "error": error}

    @classmethod
    def _validate_modern_request(
        cls,
        request_value: Mapping[str, Any],
    ) -> dict[str, Any] | None:
        request_id = request_value.get("id")
        params = request_value.get("params")
        if not isinstance(params, Mapping):
            return cls._jsonrpc_error(
                request_id,
                code=INVALID_PARAMS,
                message="Invalid params: modern MCP requests require params._meta",
                data={"missing": ["params._meta"]},
            )
        metadata = params.get("_meta")
        if not isinstance(metadata, Mapping):
            return cls._jsonrpc_error(
                request_id,
                code=INVALID_PARAMS,
                message="Invalid params: modern MCP requests require params._meta",
                data={"missing": ["params._meta"]},
            )

        missing: list[str] = []
        if META_PROTOCOL_VERSION not in metadata:
            missing.append(META_PROTOCOL_VERSION)
        if META_CLIENT_CAPABILITIES not in metadata:
            missing.append(META_CLIENT_CAPABILITIES)
        if missing:
            return cls._jsonrpc_error(
                request_id,
                code=INVALID_PARAMS,
                message="Invalid params: required modern MCP metadata is missing",
                data={"missing": missing},
            )

        requested = metadata.get(META_PROTOCOL_VERSION)
        if not isinstance(requested, str) or not requested.strip():
            return cls._jsonrpc_error(
                request_id,
                code=INVALID_PARAMS,
                message="Invalid params: protocolVersion must be a non-empty string",
                data={"field": META_PROTOCOL_VERSION},
            )
        if requested != MCP_PROTOCOL_VERSION_MODERN:
            return cls._jsonrpc_error(
                request_id,
                code=UNSUPPORTED_PROTOCOL_VERSION,
                message="Unsupported protocol version",
                data={
                    "supported": list(MCP_SUPPORTED_PROTOCOL_VERSIONS),
                    "requested": requested,
                },
            )

        client_capabilities = metadata.get(META_CLIENT_CAPABILITIES)
        if not isinstance(client_capabilities, Mapping):
            return cls._jsonrpc_error(
                request_id,
                code=INVALID_PARAMS,
                message="Invalid params: clientCapabilities must be an object",
                data={"field": META_CLIENT_CAPABILITIES},
            )
        client_info = metadata.get(META_CLIENT_INFO)
        if client_info is not None and not isinstance(client_info, Mapping):
            return cls._jsonrpc_error(
                request_id,
                code=INVALID_PARAMS,
                message="Invalid params: clientInfo must be an object when supplied",
                data={"field": META_CLIENT_INFO},
            )
        return None

    def _discover_result(self) -> dict[str, Any]:
        return {
            "resultType": "complete",
            "supportedVersions": list(MCP_SUPPORTED_PROTOCOL_VERSIONS),
            "capabilities": self._server_capabilities(MCP_PROTOCOL_VERSION_MODERN),
            "instructions": self._instructions(),
            "ttlMs": MODERN_DISCOVERY_TTL_MS,
            "cacheScope": "public",
            "_meta": {META_SERVER_INFO: self._server_info()},
        }

    def _prepare_legacy_dispatch(
        self,
        request_value: dict[str, Any],
        *,
        modern: bool,
    ) -> dict[str, Any]:
        """Suppress the historical task extension outside its legacy route."""

        if (
            not modern
            and self.negotiated_protocol_version
            == MCP_PROTOCOL_VERSION_LEGACY_TASK_EXTENSION
        ):
            return request_value
        if request_value.get("method") != "tools/call":
            return request_value

        params = request_value.get("params")
        if not isinstance(params, Mapping):
            return request_value
        metadata = params.get("_meta")
        if not isinstance(metadata, Mapping):
            return request_value
        client_capabilities = metadata.get(META_CLIENT_CAPABILITIES)
        if not isinstance(client_capabilities, Mapping):
            return request_value
        extensions = client_capabilities.get("extensions")
        if not isinstance(extensions, Mapping) or TASK_EXTENSION_ID not in extensions:
            return request_value

        prepared = deepcopy(request_value)
        prepared_params = dict(prepared.get("params") or {})
        prepared_meta = dict(prepared_params.get("_meta") or {})
        prepared_client_capabilities = dict(
            prepared_meta.get(META_CLIENT_CAPABILITIES) or {}
        )
        prepared_extensions = dict(prepared_client_capabilities.get("extensions") or {})
        prepared_extensions.pop(TASK_EXTENSION_ID, None)
        prepared_client_capabilities["extensions"] = prepared_extensions
        prepared_meta[META_CLIENT_CAPABILITIES] = prepared_client_capabilities
        prepared_params["_meta"] = prepared_meta
        prepared["params"] = prepared_params
        return prepared

    @classmethod
    def _stamp_modern_response(
        cls,
        request_value: Mapping[str, Any],
        response: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        if response is None or "error" in response:
            return response
        raw_result = response.get("result")
        if not isinstance(raw_result, Mapping):
            return response

        result = dict(raw_result)
        result.setdefault("resultType", "complete")
        metadata = dict(result.get("_meta") or {})
        metadata[META_SERVER_INFO] = cls._server_info()
        result["_meta"] = metadata

        if request_value.get("method") == "tools/list":
            tools = result.get("tools")
            if isinstance(tools, list):
                result["tools"] = sorted(
                    tools,
                    key=lambda item: (
                        str(item.get("name") or "") if isinstance(item, Mapping) else ""
                    ),
                )
            result.setdefault("ttlMs", MODERN_TOOL_LIST_TTL_MS)
            result.setdefault("cacheScope", "public")

        stamped = dict(response)
        stamped["result"] = result
        return stamped

    def handle(self, request_value: dict[str, Any]) -> dict[str, Any] | None:
        method = request_value.get("method")
        request_id = request_value.get("id")

        # Legacy era: initialize/initialized remain supported for existing MCP
        # clients and OpenAI tunnel deployments that have not migrated yet.
        if method == "notifications/initialized":
            self.client_initialized = True
            return None

        if method == "initialize":
            params = request_value.get("params") or {}
            if not isinstance(params, Mapping):
                return self._jsonrpc_error(
                    request_id,
                    code=INVALID_PARAMS,
                    message="initialize params must be an object",
                )
            negotiated = self._negotiate_legacy_protocol_version(
                params.get("protocolVersion")
            )
            client_capabilities = params.get("capabilities")
            self.client_capabilities = (
                dict(client_capabilities)
                if isinstance(client_capabilities, Mapping)
                else {}
            )
            self.negotiated_protocol_version = negotiated
            self.client_initialized = False
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "protocolVersion": negotiated,
                    "capabilities": self._server_capabilities(negotiated),
                    "serverInfo": self._server_info(),
                    "instructions": self._instructions(),
                },
            }

        modern = self._is_modern_request(request_value)
        if modern:
            validation_error = self._validate_modern_request(request_value)
            if validation_error is not None:
                return validation_error
            if method == "server/discover":
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": self._discover_result(),
                }
            # Tasks are an extension in the 2026 era. The current v76 adapter
            # is deliberately not advertised as that extension until its full
            # contemporary contract is implemented and tested.
            if method in _TASK_METHODS:
                return self._jsonrpc_error(
                    request_id,
                    code=METHOD_NOT_FOUND,
                    message="Method not found",
                )

        # 2025-11-25 also had an experimental task shape. We do not claim it.
        if method in _TASK_METHODS and (
            self.negotiated_protocol_version
            != MCP_PROTOCOL_VERSION_LEGACY_TASK_EXTENSION
        ):
            return self._jsonrpc_error(
                request_id,
                code=METHOD_NOT_FOUND,
                message="Method not found",
            )

        dispatched_request = self._prepare_legacy_dispatch(
            request_value,
            modern=modern,
        )
        response = super().handle(dispatched_request)
        response = self.turn_runtime.decorate_call_response(request_value, response)
        if modern:
            response = self._stamp_modern_response(request_value, response)
        return response


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Private stdio MCP server for Jaźń v16.")
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[2]))
    parser.add_argument("--daemon-url", default="http://127.0.0.1:8787")
    parser.add_argument("--allow-unauthenticated-local-test", action="store_true")
    parser.add_argument(
        "--trust-secure-tunnel-association",
        action="store_true",
        help="Trust the authenticated local stdio parent (for outbound Secure MCP Tunnel only).",
    )
    args = parser.parse_args(argv)
    server = JaznMcpServer(
        root=Path(args.root),
        daemon_url=args.daemon_url,
        allow_unauthenticated_local_test=args.allow_unauthenticated_local_test,
        trust_stdio_parent=args.trust_secure_tunnel_association,
    )
    return server.serve_stdio()


if __name__ == "__main__":
    raise SystemExit(main())
