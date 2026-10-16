"""Regression: slow synchronous MCP Tasks must not monopolize the ASGI loop.

This uses an isolated in-process gateway with no live daemon, network or MEMORY.
The backend intentionally holds one task request until another HTTP endpoint
has been served; a direct synchronous invocation would deadlock the loop.
"""
from __future__ import annotations

from pathlib import Path
from threading import Event
from typing import Any

import pytest

# The base Jaźń test profile intentionally has no HTTP/MCP extras. Skip
# before importing their transitive dependencies such as AnyIO.
pytest.importorskip("mcp")
httpx = pytest.importorskip("httpx")
import anyio

from latka_jazn.mcp.http_gateway import build_public_mcp_gateway


class _NoopPublicBackend:
    """Keep the production-like gateway public tool adapter independent.

    Supplying a public backend is required so the gateway actually uses the
    injected synthetic protocol backend, rather than its real private server.
    """

    def call_tool(
        self, name: str, arguments: dict[str, Any],
        *, meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        raise AssertionError("a Tasks-only HTTP test must not invoke public tools")


class _BlockingProtocolBackend:
    def __init__(self) -> None:
        self.entered = Event()
        self.release = Event()
        self.calls = 0
        self.observed_subject: str | None = None

    def handle(self, request_value: dict[str, Any]) -> dict[str, Any]:
        raise AssertionError("authenticated HTTP Tasks must use verified dispatch")

    def handle_public_authenticated(
        self, request_value: dict[str, Any], *,
        owner_subject: str, owner_transport: str,
    ) -> dict[str, Any]:
        self.calls += 1
        self.observed_subject = owner_subject
        assert owner_transport == "public_http"
        self.entered.set()
        if not self.release.wait(timeout=4):
            raise RuntimeError("synthetic_task_backend_wait_expired")
        return {
            "jsonrpc": "2.0",
            "id": request_value["id"],
            "result": {"status": "working", "taskId": "opaque-task-1"},
        }


def _task_request() -> tuple[dict[str, str], dict[str, Any]]:
    return (
        {
            "mcp-protocol-version": "2026-07-28",
            "mcp-method": "tasks/get",
            "mcp-name": "opaque-task-1",
        },
        {
            "jsonrpc": "2.0",
            "id": 7,
            "method": "tasks/get",
            "params": {
                "taskId": "opaque-task-1",
                "_meta": {
                    "io.modelcontextprotocol/protocolVersion": "2026-07-28",
                    "io.modelcontextprotocol/clientCapabilities": {
                        "extensions": {"io.modelcontextprotocol/tasks": {}},
                    },
                },
            },
        },
    )


@pytest.mark.anyio
async def test_tasks_backend_does_not_block_unrelated_healthz(tmp_path: Path) -> None:
    backend = _BlockingProtocolBackend()
    gateway = build_public_mcp_gateway(
        root=tmp_path,
        backend=_NoopPublicBackend(),
        protocol_backend=backend,
        allow_unauthenticated_loopback_dev=True,
    )
    headers, payload = _task_request()
    responses: list[Any] = []

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=gateway.asgi_app()),
        base_url="http://127.0.0.1:8080",
    ) as client:
        async def task_call() -> None:
            responses.append(await client.post("/mcp", headers=headers, json=payload))

        try:
            async with anyio.create_task_group() as group:
                group.start_soon(task_call)
                with anyio.fail_after(2):
                    started = await anyio.to_thread.run_sync(backend.entered.wait, 1)
                    assert started, f"task backend did not start; early HTTP responses: {[str(response.text) for response in responses]}"
                # The worker has not been released, yet the event loop must
                # remain responsive to this independent HTTP request.
                with anyio.fail_after(1.5):
                    health = await client.get("/healthz")
                assert health.status_code == 200
                assert health.json()["gateway_live"] is True
                assert not backend.release.is_set()
                backend.release.set()
        finally:
            backend.release.set()

    assert backend.calls == 1
    assert backend.observed_subject == "loopback-development"
    assert len(responses) == 1
    assert responses[0].status_code == 200
    assert responses[0].json()["result"]["taskId"] == "opaque-task-1"


@pytest.mark.anyio
async def test_task_backend_exception_remains_fail_closed_without_replay(tmp_path: Path) -> None:
    class _FailingBackend:
        calls = 0

        def handle(self, request_value: dict[str, Any]) -> dict[str, Any]:
            raise AssertionError("authenticated HTTP Tasks must use verified dispatch")

        def handle_public_authenticated(
            self, request_value: dict[str, Any], *,
            owner_subject: str, owner_transport: str,
        ) -> dict[str, Any]:
            self.calls += 1
            raise RuntimeError("synthetic backend failure - do not expose")

    backend = _FailingBackend()
    gateway = build_public_mcp_gateway(
        root=tmp_path,
        backend=_NoopPublicBackend(),
        protocol_backend=backend,
        allow_unauthenticated_loopback_dev=True,
    )
    headers, payload = _task_request()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=gateway.asgi_app()),
        base_url="http://127.0.0.1:8080",
    ) as client:
        response = await client.post("/mcp", headers=headers, json=payload)
    assert response.status_code == 200
    result = response.json()
    assert result["id"] == 7
    assert result["error"]["code"] == -32603, result["error"]
    assert result["error"]["message"] == "Internal MCP task bridge error"
    assert backend.calls == 1
