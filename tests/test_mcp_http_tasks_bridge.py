from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("mcp")

from starlette.testclient import TestClient

from latka_jazn.mcp.http_gateway import (
    SCOPE_CONNECT,
    SCOPE_TASK_CANCEL,
    SCOPE_TASK_READ,
    SCOPE_TASK_UPDATE,
    SCOPE_TURN_SUBMIT,
    build_public_mcp_gateway,
)
from latka_jazn.mcp.server import (
    MCP_PROTOCOL_VERSION_MODERN,
    META_CLIENT_CAPABILITIES,
    META_PROTOCOL_VERSION,
    TASK_EXTENSION_ID,
)


class _Backend:
    def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
        *,
        meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if name == "jazn_status":
            return {
                "content": [{"type": "text", "text": "ok"}],
                "structuredContent": {
                    "gateway_ok": True,
                    "daemon_reachable": True,
                    "capability_matrix": {"conversation_ready": True},
                },
                "_meta": {},
                "isError": False,
            }
        raise AssertionError(name)


class _ProtocolBackend:
    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []

    def handle(self, request_value: dict[str, Any]) -> dict[str, Any]:
        self.requests.append(request_value)
        method = str(request_value["method"])
        if method == "tools/call":
            return {
                "jsonrpc": "2.0",
                "id": request_value["id"],
                "result": {
                    "resultType": "task",
                    "taskId": "jazn-task-test",
                    "status": "working",
                    "createdAt": "2026-09-20T00:00:00+00:00",
                    "lastUpdatedAt": "2026-09-20T00:00:00+00:00",
                    "ttlMs": 3600000,
                    "pollIntervalMs": 750,
                },
            }
        return {
            "jsonrpc": "2.0",
            "id": request_value["id"],
            "result": {
                "resultType": "complete",
                "taskId": "jazn-task-test",
                "status": "working",
                "createdAt": "2026-09-20T00:00:00+00:00",
                "lastUpdatedAt": "2026-09-20T00:00:00+00:00",
                "ttlMs": 3600000,
                "pollIntervalMs": 750,
            },
        }


def _meta() -> dict[str, Any]:
    return {
        META_PROTOCOL_VERSION: MCP_PROTOCOL_VERSION_MODERN,
        META_CLIENT_CAPABILITIES: {
            "extensions": {
                TASK_EXTENSION_ID: {},
            }
        },
    }


def _headers(method: str, name: str) -> dict[str, str]:
    return {
        "content-type": "application/json",
        "MCP-Protocol-Version": MCP_PROTOCOL_VERSION_MODERN,
        "Mcp-Method": method,
        "Mcp-Name": name,
    }


def _gateway(tmp_path: Path, protocol: _ProtocolBackend):
    return build_public_mcp_gateway(
        root=tmp_path,
        backend=_Backend(),
        protocol_backend=protocol,
        allow_unauthenticated_loopback_dev=True,
    )


def test_tasks_extension_is_advertised_when_protocol_backend_is_available(tmp_path: Path) -> None:
    protocol = _ProtocolBackend()
    gateway = _gateway(tmp_path, protocol)
    with TestClient(gateway.asgi_app(), base_url="http://127.0.0.1:8080") as client:
        response = client.post(
            "/mcp",
            headers={
                "content-type": "application/json",
                "MCP-Protocol-Version": MCP_PROTOCOL_VERSION_MODERN,
                "Mcp-Method": "server/discover",
            },
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "server/discover",
                "params": {"_meta": _meta()},
            },
        )
    assert response.status_code == 200
    payload = response.json()
    assert TASK_EXTENSION_ID in payload["result"]["capabilities"]["extensions"]


def test_task_capable_generate_is_intercepted_and_keeps_internal_auth_private(tmp_path: Path) -> None:
    protocol = _ProtocolBackend()
    gateway = _gateway(tmp_path, protocol)
    body = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/call",
        "params": {
            "name": "jazn_generate_visible_reply",
            "arguments": {
                "request_id": "req-task-http",
                "message": "hello",
            },
            "_meta": _meta(),
        },
    }
    with TestClient(gateway.asgi_app(), base_url="http://127.0.0.1:8080") as client:
        response = client.post(
            "/mcp",
            headers=_headers("tools/call", "jazn_generate_visible_reply"),
            content=json.dumps(body),
        )

    assert response.status_code == 200
    assert response.json()["result"]["resultType"] == "task"
    assert protocol.requests
    forwarded_meta = protocol.requests[-1]["params"]["_meta"]
    assert forwarded_meta["authorization"]
    assert forwarded_meta["subject"] == "loopback-development"


def test_task_http_bridge_rejects_mcp_name_mismatch(tmp_path: Path) -> None:
    protocol = _ProtocolBackend()
    gateway = _gateway(tmp_path, protocol)
    body = {
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tasks/get",
        "params": {"taskId": "jazn-task-test", "_meta": _meta()},
    }
    with TestClient(gateway.asgi_app(), base_url="http://127.0.0.1:8080") as client:
        response = client.post(
            "/mcp",
            headers=_headers("tasks/get", "wrong-task"),
            content=json.dumps(body),
        )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == -32020
    assert protocol.requests == []


def test_task_http_bridge_routes_all_task_methods(tmp_path: Path) -> None:
    protocol = _ProtocolBackend()
    gateway = _gateway(tmp_path, protocol)
    with TestClient(gateway.asgi_app(), base_url="http://127.0.0.1:8080") as client:
        for request_id, method in enumerate(
            ("tasks/get", "tasks/update", "tasks/cancel"),
            start=10,
        ):
            params: dict[str, Any] = {
                "taskId": "jazn-task-test",
                "_meta": _meta(),
            }
            if method == "tasks/update":
                params["inputResponses"] = {"confirm": True}
            response = client.post(
                "/mcp",
                headers=_headers(method, "jazn-task-test"),
                content=json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "method": method,
                        "params": params,
                    }
                ),
            )
            assert response.status_code == 200
    assert [item["method"] for item in protocol.requests] == [
        "tasks/get",
        "tasks/update",
        "tasks/cancel",
    ]


def test_loopback_dev_principal_contains_explicit_task_scopes(tmp_path: Path) -> None:
    protocol = _ProtocolBackend()
    gateway = _gateway(tmp_path, protocol)
    principal = gateway._principal()
    assert principal is not None
    assert {
        SCOPE_CONNECT,
        SCOPE_TURN_SUBMIT,
        SCOPE_TASK_READ,
        SCOPE_TASK_UPDATE,
        SCOPE_TASK_CANCEL,
    }.issubset(principal.scopes)


def test_task_capable_generate_rejects_oversized_message_before_backend(tmp_path: Path) -> None:
    protocol = _ProtocolBackend()
    gateway = _gateway(tmp_path, protocol)
    body = {
        "jsonrpc": "2.0",
        "id": 40,
        "method": "tools/call",
        "params": {
            "name": "jazn_generate_visible_reply",
            "arguments": {
                "request_id": "req-oversized",
                "message": "x" * 262_145,
            },
            "_meta": _meta(),
        },
    }
    with TestClient(gateway.asgi_app(), base_url="http://127.0.0.1:8080") as client:
        response = client.post(
            "/mcp",
            headers=_headers("tools/call", "jazn_generate_visible_reply"),
            content=json.dumps(body),
        )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == -32602
    assert protocol.requests == []


def test_task_capable_generate_shares_public_rate_limit(tmp_path: Path) -> None:
    protocol = _ProtocolBackend()
    gateway = _gateway(tmp_path, protocol)
    with TestClient(gateway.asgi_app(), base_url="http://127.0.0.1:8080") as client:
        for index in range(10):
            body = {
                "jsonrpc": "2.0",
                "id": 50 + index,
                "method": "tools/call",
                "params": {
                    "name": "jazn_generate_visible_reply",
                    "arguments": {
                        "request_id": f"req-rate-{index}",
                        "message": "hello",
                    },
                    "_meta": _meta(),
                },
            }
            response = client.post(
                "/mcp",
                headers=_headers("tools/call", "jazn_generate_visible_reply"),
                content=json.dumps(body),
            )
            assert response.status_code == 200

        blocked = client.post(
            "/mcp",
            headers=_headers("tools/call", "jazn_generate_visible_reply"),
            content=json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 99,
                    "method": "tools/call",
                    "params": {
                        "name": "jazn_generate_visible_reply",
                        "arguments": {
                            "request_id": "req-rate-blocked",
                            "message": "hello",
                        },
                        "_meta": _meta(),
                    },
                }
            ),
        )

    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == -32029
    assert len(protocol.requests) == 10
