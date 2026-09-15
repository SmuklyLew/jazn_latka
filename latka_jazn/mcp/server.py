from __future__ import annotations

"""MCP 2025-11-25 negotiation shim over the byte-exact v76 server.

The v76 implementation remains preserved as ``server_legacy_v76`` so the
release patch stays auditable.  This module narrows only protocol negotiation
and the legacy Tasks compatibility surface; tool execution, auth, audit,
idempotency and Jaźń finalization remain owned by the preserved server.
"""

import argparse
from pathlib import Path
from typing import Any, Mapping

from latka_jazn.mcp.server_legacy_v76 import *  # noqa: F401,F403
from latka_jazn.mcp.server_legacy_v76 import (
    JaznMcpServer as _V76JaznMcpServer,
    TASK_EXTENSION_ID,
)
from latka_jazn.version import PACKAGE_VERSION_FULL

MCP_PROTOCOL_VERSION_LATEST = "2025-11-25"
MCP_PROTOCOL_VERSION_LEGACY_TASK_EXTENSION = "2025-06-18"
MCP_SUPPORTED_PROTOCOL_VERSIONS = (
    MCP_PROTOCOL_VERSION_LATEST,
    MCP_PROTOCOL_VERSION_LEGACY_TASK_EXTENSION,
)


class JaznMcpServer(_V76JaznMcpServer):
    """v76.1 protocol/capability convergence without changing tool semantics."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.negotiated_protocol_version: str | None = None
        self.client_capabilities: dict[str, Any] = {}
        self.client_initialized = False

    @staticmethod
    def _negotiate_protocol_version(requested: Any) -> str:
        candidate = str(requested or "").strip()
        if candidate in MCP_SUPPORTED_PROTOCOL_VERSIONS:
            return candidate
        return MCP_PROTOCOL_VERSION_LATEST

    def _client_supports_tasks(self, metadata: Mapping[str, Any]) -> bool:
        # Jaźń's existing task adapter predates standard MCP 2025-11-25 Tasks.
        # Keep it only as a bounded legacy extension on the protocol where it
        # was introduced; never advertise partial standard-Tasks support.
        if self.negotiated_protocol_version != MCP_PROTOCOL_VERSION_LEGACY_TASK_EXTENSION:
            return False
        capabilities = metadata.get("io.modelcontextprotocol/clientCapabilities")
        if not isinstance(capabilities, Mapping):
            return False
        extensions = capabilities.get("extensions")
        return isinstance(extensions, Mapping) and TASK_EXTENSION_ID in extensions

    def _server_capabilities(self, protocol_version: str | None = None) -> dict[str, Any]:
        resolved = protocol_version or self.negotiated_protocol_version or MCP_PROTOCOL_VERSION_LATEST
        capabilities: dict[str, Any] = {"tools": {"listChanged": False}}
        if resolved == MCP_PROTOCOL_VERSION_LEGACY_TASK_EXTENSION:
            capabilities["extensions"] = {TASK_EXTENSION_ID: {}}
        return capabilities

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
                    "serverInfo": {"name": "jazn-private-mcp", "version": PACKAGE_VERSION_FULL},
                    "instructions": (
                        "Use jazn_generate_visible_reply once per new user turn with a stable request_id; "
                        "resume pending work with jazn_resume_visible_reply using the same daemon_request_id; "
                        "finalize generate_then_finalize responses with jazn_finalize_reply."
                    ),
                },
            }

        if method in {"tasks/get", "tasks/cancel", "tasks/update"} and (
            self.negotiated_protocol_version != MCP_PROTOCOL_VERSION_LEGACY_TASK_EXTENSION
        ):
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32601, "message": "Method not found"},
            }

        return super().handle(request_value)


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
