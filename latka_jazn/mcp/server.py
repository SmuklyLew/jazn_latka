from __future__ import annotations

"""MCP 2025-11-25 negotiation and typed Jaźń turn-runtime convergence.

The byte-exact v76 server remains the implementation owner for tool execution,
authentication, audit, idempotency and finalization. This module owns protocol
negotiation plus the transport-facing typed turn contract used by ChatGPT.
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

MCP_PROTOCOL_VERSION_LATEST = "2025-11-25"
MCP_PROTOCOL_VERSION_LEGACY_TASK_EXTENSION = "2025-06-18"
MCP_SUPPORTED_PROTOCOL_VERSIONS = (
    MCP_PROTOCOL_VERSION_LATEST,
    MCP_PROTOCOL_VERSION_LEGACY_TASK_EXTENSION,
)


def __getattr__(name: str) -> Any:
    """Preserve runtime compatibility for non-canonical legacy module exports.

    New code should import the explicit public names from this module. The
    fallback exists only so older integrations that reached through
    ``latka_jazn.mcp.server`` do not break during the convergence release.
    """

    return getattr(_legacy, name)


class JaznMcpServer(_V76JaznMcpServer):
    """Modern protocol facade over the single canonical Jaźń runtime."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.negotiated_protocol_version: str | None = None
        self.client_capabilities: dict[str, Any] = {}
        self.client_initialized = False
        self.turn_runtime = McpTurnRuntimeAdapter()

    @staticmethod
    def _negotiate_protocol_version(requested: Any) -> str:
        candidate = str(requested or "").strip()
        if candidate in MCP_SUPPORTED_PROTOCOL_VERSIONS:
            return candidate
        return MCP_PROTOCOL_VERSION_LATEST

    def _server_capabilities(self, protocol_version: str | None = None) -> dict[str, Any]:
        resolved = protocol_version or self.negotiated_protocol_version or MCP_PROTOCOL_VERSION_LATEST
        capabilities: dict[str, Any] = {
            "tools": {"listChanged": False},
            "experimental": {
                TURN_RUNTIME_CAPABILITY: self.turn_runtime.capability_descriptor(),
            },
        }
        if resolved == MCP_PROTOCOL_VERSION_LEGACY_TASK_EXTENSION:
            capabilities["extensions"] = {TASK_EXTENSION_ID: {}}
        return capabilities

    def _prepare_legacy_dispatch(self, request_value: dict[str, Any]) -> dict[str, Any]:
        """Remove the pre-standard task extension on modern MCP sessions.

        v76 may wrap a pending generate call as its historical task extension
        when the client sends that extension in ``_meta``. For a negotiated
        2025-11-25 session that would look like partial standard Tasks support,
        so the modern facade suppresses the old extension before dispatch.
        Legacy 2025-06-18 sessions are passed byte-for-byte to the old server.
        """

        if self.negotiated_protocol_version == MCP_PROTOCOL_VERSION_LEGACY_TASK_EXTENSION:
            return request_value
        if request_value.get("method") != "tools/call":
            return request_value

        params = request_value.get("params")
        if not isinstance(params, Mapping):
            return request_value
        metadata = params.get("_meta")
        if not isinstance(metadata, Mapping):
            return request_value
        client_capabilities = metadata.get("io.modelcontextprotocol/clientCapabilities")
        if not isinstance(client_capabilities, Mapping):
            return request_value
        extensions = client_capabilities.get("extensions")
        if not isinstance(extensions, Mapping) or TASK_EXTENSION_ID not in extensions:
            return request_value

        prepared = deepcopy(request_value)
        prepared_params = dict(prepared.get("params") or {})
        prepared_meta = dict(prepared_params.get("_meta") or {})
        prepared_client_capabilities = dict(
            prepared_meta.get("io.modelcontextprotocol/clientCapabilities") or {}
        )
        prepared_extensions = dict(prepared_client_capabilities.get("extensions") or {})
        prepared_extensions.pop(TASK_EXTENSION_ID, None)
        prepared_client_capabilities["extensions"] = prepared_extensions
        prepared_meta["io.modelcontextprotocol/clientCapabilities"] = prepared_client_capabilities
        prepared_params["_meta"] = prepared_meta
        prepared["params"] = prepared_params
        return prepared

    def handle(self, request_value: dict[str, Any]) -> dict[str, Any] | None:
        method = request_value.get("method")
        request_id = request_value.get("id")

        if method == "notifications/initialized":
            self.client_initialized = True
            return None

        if method == "initialize":
            params = request_value.get("params") or {}
            if not isinstance(params, Mapping):
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {"code": -32001, "message": "initialize params must be an object"},
                }
            negotiated = self._negotiate_protocol_version(params.get("protocolVersion"))
            client_capabilities = params.get("capabilities")
            self.client_capabilities = (
                dict(client_capabilities) if isinstance(client_capabilities, Mapping) else {}
            )
            self.negotiated_protocol_version = negotiated
            self.client_initialized = False
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "protocolVersion": negotiated,
                    "capabilities": self._server_capabilities(negotiated),
                    "serverInfo": {
                        "name": "jazn-private-mcp",
                        "version": PACKAGE_VERSION_FULL,
                        "description": (
                            "Private Jaźń MCP bridge with stable request identity, "
                            "typed turn phases and fail-closed visible-output finalization."
                        ),
                    },
                    "instructions": (
                        "Use jazn_generate_visible_reply exactly once for a new user turn with a stable request_id. "
                        "If action=poll_runtime, call jazn_resume_visible_reply with the same daemon_request_id and "
                        "never replay the user message. If action=generate_then_finalize, generate only from the "
                        "returned host contract and finish with jazn_finalize_reply. Display Jaźń output only when "
                        "the returned action is display_exact."
                    ),
                },
            }

        # MCP 2025-11-25 Tasks are experimental and have a complete standardized
        # lifecycle (list/get/result/cancel plus capability negotiation). The
        # preserved v76 adapter is intentionally not presented as that standard.
        if method in {"tasks/get", "tasks/list", "tasks/result", "tasks/cancel", "tasks/update"} and (
            self.negotiated_protocol_version != MCP_PROTOCOL_VERSION_LEGACY_TASK_EXTENSION
        ):
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32601, "message": "Method not found"},
            }

        dispatched_request = self._prepare_legacy_dispatch(request_value)
        response = super().handle(dispatched_request)
        return self.turn_runtime.decorate_call_response(request_value, response)


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
