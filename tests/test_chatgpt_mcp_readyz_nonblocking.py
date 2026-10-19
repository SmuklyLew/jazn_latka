"""Slow daemon status checks must not block independent MCP liveness checks."""
from __future__ import annotations

from pathlib import Path
from threading import Event
from typing import Any

import pytest

pytest.importorskip("mcp")
httpx = pytest.importorskip("httpx")
import anyio

from latka_jazn.mcp.http_gateway import build_public_mcp_gateway
from latka_jazn.version import PACKAGE_VERSION_FULL


class _BlockingStatusBackend:
    def __init__(self) -> None:
        self.entered = Event()
        self.release = Event()
        self.calls = 0

    def call_tool(
        self, name: str, arguments: dict[str, Any],
        *, meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        assert name == "jazn_status"
        self.calls += 1
        self.entered.set()
        if not self.release.wait(timeout=4):
            raise RuntimeError("synthetic status backend timeout")
        return {
            "structuredContent": {
                "ok": True,
                "ready": True,
                "gateway_live": True,
                "daemon_reachable": True,
                "runtime_root": "/secret/must/not/leak",
                "daemon": {
                    "daemon_instance_id": "test-daemon",
                    "runtime_version": PACKAGE_VERSION_FULL,
                    "last_heartbeat_at_utc": "2026-10-19T18:00:00+00:00",
                },
                "capability_matrix": {"conversation_ready": True},
            },
        }


@pytest.mark.anyio
async def test_readyz_status_io_does_not_block_healthz(tmp_path: Path) -> None:
    backend = _BlockingStatusBackend()
    gateway = build_public_mcp_gateway(
        root=tmp_path,
        backend=backend,
        allow_unauthenticated_loopback_dev=True,
    )
    responses: list[Any] = []

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=gateway.asgi_app()),
        base_url="http://127.0.0.1:8080",
    ) as client:
        async def ready_call() -> None:
            responses.append(await client.get("/readyz"))

        try:
            async with anyio.create_task_group() as group:
                group.start_soon(ready_call)
                with anyio.fail_after(2):
                    started = await anyio.to_thread.run_sync(backend.entered.wait, 1)
                    assert started, "readiness backend did not start"
                # The backend is blocked in a worker; the event loop must
                # still serve another HTTP endpoint without releasing it.
                with anyio.fail_after(2):
                    health = await client.get("/healthz")
                assert health.status_code == 200
                assert health.json()["gateway_live"] is True
                assert not backend.release.is_set()
                backend.release.set()
        finally:
            backend.release.set()

    assert backend.calls == 1
    assert len(responses) == 1
    assert responses[0].status_code in (200, 503)
    assert "runtime_root" not in responses[0].json()
