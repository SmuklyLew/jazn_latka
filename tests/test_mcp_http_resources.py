from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("mcp")

from mcp import Client
from mcp.types import TextResourceContents

from latka_jazn.mcp.http_gateway import build_public_mcp_gateway
from latka_jazn.mcp.task_resume import McpTaskStore


class _Backend:
    def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
        *,
        meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if name != "jazn_status":
            raise AssertionError(name)
        return {
            "content": [{"type": "text", "text": "private"}],
            "structuredContent": {
                "gateway_ok": True,
                "daemon_reachable": True,
                "runtime_root": "MUST-NOT-LEAK",
                "capability_matrix": {
                    "conversation_ready": True,
                    "ordinary_dialogue_allowed": True,
                    "components": {
                        "persistent_memory": {
                            "status": "optional_absent",
                            "available": False,
                            "required_for_dialogue": False,
                            "reason": "memory_not_attached",
                            "evidence": {"private": "must-not-leak"},
                        },
                        "recall": {
                            "status": "memory_not_attached",
                            "available": False,
                            "required_for_dialogue": False,
                            "reason": "memory_not_attached",
                            "evidence": {"private": "must-not-leak"},
                        },
                    },
                },
            },
            "_meta": {"private": True},
            "isError": False,
        }


def _resource_text(result: Any) -> str:
    content = result.contents[0]
    assert isinstance(content, TextResourceContents)
    return content.text


def _gateway(tmp_path: Path):
    return build_public_mcp_gateway(
        root=tmp_path,
        backend=_Backend(),
        allow_unauthenticated_loopback_dev=True,
    )


@pytest.mark.anyio
async def test_http_gateway_exposes_redacted_runtime_and_memory_resources(tmp_path: Path) -> None:
    gateway = _gateway(tmp_path)
    async with Client(gateway.mcp, raise_exceptions=True) as client:
        resources = await client.list_resources()
        runtime = await client.read_resource("jazn://runtime/status")
        memory = await client.read_resource("jazn://memory/status")

    uris = {str(item.uri) for item in resources.resources}
    assert "jazn://runtime/status" in uris
    assert "jazn://memory/status" in uris

    runtime_payload = json.loads(_resource_text(runtime))
    memory_payload = json.loads(_resource_text(memory))
    assert runtime_payload["ready"] is True
    assert runtime_payload["daemon_reachable"] is True
    assert "runtime_root" not in runtime_payload
    assert memory_payload["persistent_memory"]["available"] is False
    assert "evidence" not in memory_payload["persistent_memory"]


@pytest.mark.anyio
async def test_http_gateway_task_resource_reads_same_durable_registry(tmp_path: Path) -> None:
    task = McpTaskStore(tmp_path).create_or_get(
        daemon_request_id="req-resource-durable",
        request_id="req-resource-durable",
        turn_id="turn-resource-durable",
        trace_id="trace-resource-durable",
    )
    gateway = _gateway(tmp_path)
    async with Client(gateway.mcp, raise_exceptions=True) as client:
        result = await client.read_resource(f"jazn://task/{task.task_id}")

    payload = json.loads(_resource_text(result))
    assert payload["task"]["taskId"] == task.task_id
    assert payload["lineage"]["daemon_request_id"] == "req-resource-durable"
    assert payload["lineage"]["turn_id"] == "turn-resource-durable"
