from __future__ import annotations

from pathlib import Path
from typing import Any

from latka_jazn.mcp.server import (
    MCP_PROTOCOL_VERSION_LATEST_LEGACY,
    MCP_PROTOCOL_VERSION_MODERN,
    MCP_SUPPORTED_PROTOCOL_VERSIONS,
    META_CLIENT_CAPABILITIES,
    META_PROTOCOL_VERSION,
    META_SERVER_INFO,
    TASK_EXTENSION_ID,
    JaznMcpServer,
)


def _server(root: Path) -> JaznMcpServer:
    return JaznMcpServer(root=root, allow_unauthenticated_local_test=True)


def _modern_meta(*, version: str = MCP_PROTOCOL_VERSION_MODERN, capabilities: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        META_PROTOCOL_VERSION: version,
        META_CLIENT_CAPABILITIES: dict(capabilities or {}),
    }


def _modern_request(method: str, *, request_id: int = 1, params: dict[str, Any] | None = None) -> dict[str, Any]:
    value = dict(params or {})
    value.setdefault("_meta", _modern_meta())
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": method,
        "params": value,
    }


def test_server_discover_exposes_modern_and_legacy_versions_without_tasks_extension(tmp_path: Path) -> None:
    server = _server(tmp_path)
    response = server.handle(_modern_request("server/discover", request_id=10))

    assert response is not None
    result = response["result"]
    assert result["resultType"] == "complete"
    assert result["supportedVersions"] == list(MCP_SUPPORTED_PROTOCOL_VERSIONS)
    assert result["capabilities"]["tools"]["listChanged"] is False
    assert TASK_EXTENSION_ID not in result["capabilities"].get("extensions", {})
    assert result["_meta"][META_SERVER_INFO]["name"] == "jazn-private-mcp"
    assert result["ttlMs"] > 0
    assert result["cacheScope"] == "public"


def test_modern_tools_list_is_stamped_cacheable_and_deterministic(tmp_path: Path) -> None:
    server = _server(tmp_path)
    response = server.handle(_modern_request("tools/list", request_id=11))

    assert response is not None
    result = response["result"]
    assert result["resultType"] == "complete"
    assert result["ttlMs"] > 0
    assert result["cacheScope"] == "public"
    assert result["_meta"][META_SERVER_INFO]["version"]
    names = [str(tool["name"]) for tool in result["tools"]]
    assert names == sorted(names)


def test_modern_request_missing_required_meta_fails_invalid_params(tmp_path: Path) -> None:
    server = _server(tmp_path)
    response = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 12,
            "method": "server/discover",
            "params": {"_meta": {META_PROTOCOL_VERSION: MCP_PROTOCOL_VERSION_MODERN}},
        }
    )

    assert response is not None
    assert response["error"]["code"] == -32602
    assert META_CLIENT_CAPABILITIES in response["error"]["data"]["missing"]


def test_unsupported_modern_protocol_reports_requested_and_supported_versions(tmp_path: Path) -> None:
    server = _server(tmp_path)
    response = server.handle(
        _modern_request(
            "server/discover",
            request_id=13,
            params={"_meta": _modern_meta(version="2099-01-01")},
        )
    )

    assert response is not None
    assert response["error"]["code"] == -32022
    assert response["error"]["data"]["requested"] == "2099-01-01"
    assert response["error"]["data"]["supported"] == list(MCP_SUPPORTED_PROTOCOL_VERSIONS)


def test_initialize_never_negotiates_the_handshake_free_modern_revision(tmp_path: Path) -> None:
    server = _server(tmp_path)
    response = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 14,
            "method": "initialize",
            "params": {
                "protocolVersion": MCP_PROTOCOL_VERSION_MODERN,
                "capabilities": {},
                "clientInfo": {"name": "legacy-probe", "version": "1"},
            },
        }
    )

    assert response is not None
    assert response["result"]["protocolVersion"] == MCP_PROTOCOL_VERSION_LATEST_LEGACY
    assert response["result"]["protocolVersion"] != MCP_PROTOCOL_VERSION_MODERN


def test_modern_tasks_methods_are_not_claimed_without_current_extension_implementation(tmp_path: Path) -> None:
    server = _server(tmp_path)
    for index, method in enumerate(("tasks/get", "tasks/update", "tasks/cancel"), start=20):
        response = server.handle(_modern_request(method, request_id=index))
        assert response is not None
        assert response["error"]["code"] == -32601


def test_modern_requests_do_not_mutate_legacy_connection_capabilities(tmp_path: Path) -> None:
    server = _server(tmp_path)
    first_caps = {"experimental": {"example": {"enabled": True}}}
    first = server.handle(
        _modern_request(
            "server/discover",
            request_id=30,
            params={"_meta": _modern_meta(capabilities=first_caps)},
        )
    )
    second = server.handle(_modern_request("server/discover", request_id=31))

    assert first is not None and second is not None
    assert server.client_capabilities == {}
    assert server.negotiated_protocol_version is None
    assert server.client_initialized is False


def test_modern_dispatch_strips_historical_task_extension_before_legacy_tool_execution(tmp_path: Path) -> None:
    server = _server(tmp_path)
    request = _modern_request(
        "tools/call",
        request_id=40,
        params={
            "name": "jazn_generate_visible_reply",
            "arguments": {"message": "hello", "request_id": "req-40"},
            "_meta": _modern_meta(
                capabilities={"extensions": {TASK_EXTENSION_ID: {}}}
            ),
        },
    )

    prepared = server._prepare_legacy_dispatch(request, modern=True)
    prepared_extensions = prepared["params"]["_meta"][META_CLIENT_CAPABILITIES]["extensions"]
    original_extensions = request["params"]["_meta"][META_CLIENT_CAPABILITIES]["extensions"]
    assert TASK_EXTENSION_ID not in prepared_extensions
    assert TASK_EXTENSION_ID in original_extensions
