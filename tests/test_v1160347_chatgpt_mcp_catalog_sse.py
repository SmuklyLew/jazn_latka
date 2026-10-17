"""MCP 2026-07-28 tools/list via Streamable HTTP SSE: bounded, read-only."""
from __future__ import annotations

from io import BytesIO
import json
from typing import Any
import urllib.request

import pytest

from latka_jazn.mcp import chatgpt_bridge_probe as probe
from latka_jazn.mcp.chatgpt_toolset import REQUIRED_CHATGPT_TURN_TOOLS


def tool(name: str) -> dict[str, Any]:
    return {
        "name": name,
        "description": "canonical runtime tool",
        "inputSchema": {"type": "object", "properties": {}},
        "annotations": {
            "readOnlyHint": name in {"jazn_status", "jazn_resume_visible_reply"},
            "destructiveHint": False,
            "openWorldHint": False,
            "idempotentHint": True,
        },
        "_meta": {
            "ui": {"visibility": ["model", "app"]},
            "securitySchemes": [{"type": "oauth2", "scopes": ["jazn:mcp:connect"]}],
        },
    }


def result(page: int, names: list[str], cursor: str | None = None) -> bytes:
    payload: dict[str, Any] = {"resultType": "complete", "tools": [tool(n) for n in names]}
    if cursor is not None:
        payload["nextCursor"] = cursor
    return json.dumps({"jsonrpc": "2.0", "id": page, "result": payload}).encode()


def event(data: bytes) -> bytes:
    return b"event: message\ndata: " + data + b"\n\n"


class Response(BytesIO):
    status = 200
    def __init__(self, stream: bytes) -> None:
        super().__init__(stream)
        self.headers = {"Content-Type": "text/event-stream; charset=utf-8"}


def install(monkeypatch: pytest.MonkeyPatch, pages: list[bytes]) -> list[urllib.request.Request]:
    calls: list[urllib.request.Request] = []

    class Opener:
        def open(self, request: urllib.request.Request, *, timeout: float) -> Response:
            assert 0.1 <= timeout <= 30.0
            assert request.get_header("Mcp-method") == "tools/list"
            assert json.loads(request.data or b"{}")["method"] == "tools/list"
            calls.append(request)
            return Response(pages[len(calls) - 1])

    monkeypatch.setattr(probe.urllib.request, "build_opener", lambda *args: Opener())
    return calls


def test_valid_sse_returns_verified_catalog_only(monkeypatch: pytest.MonkeyPatch) -> None:
    body = b": keepalive\n\n" + event(result(1, list(REQUIRED_CHATGPT_TURN_TOOLS))) + b": trailing ignored"
    calls = install(monkeypatch, [body])
    observed = probe.probe_chatgpt_mcp_tool_catalog("https://mcp.example.org/mcp")
    assert observed["ok"] is True
    assert observed["pages_checked"] == 1
    assert observed["chatgpt_current_message_toolset_verified"] is False
    assert observed["daemon_conversation_ready_verified"] is False
    assert observed["accepted_visible_turn_verified"] is False
    assert len(calls) == 1


def test_sse_multipage_and_notification(monkeypatch: pytest.MonkeyPatch) -> None:
    notification = event(b'{"jsonrpc":"2.0","method":"notifications/progress","params":{}}')
    one = notification + event(result(1, [REQUIRED_CHATGPT_TURN_TOOLS[0]], "more"))
    two = event(result(2, list(REQUIRED_CHATGPT_TURN_TOOLS[1:])))
    calls = install(monkeypatch, [one, two])
    found = probe.probe_chatgpt_mcp_tool_catalog("https://mcp.example.org/mcp")
    assert found["ok"] is True
    assert found["pages_checked"] == 2
    assert len(calls) == 2


@pytest.mark.parametrize(("stream", "reason"), [
    (b": ping\n\n", "mcp_catalog_sse_incomplete"),
    (b"event: message\ndata: {notjson}\n\n", "mcp_catalog_sse_invalid_json"),
    (event(result(2, list(REQUIRED_CHATGPT_TURN_TOOLS))), "mcp_catalog_sse_wrong_request_id"),
    (b"event: error\ndata: nope\n\n", "mcp_catalog_sse_unexpected_event"),
    (b"data: partial\n", "mcp_catalog_sse_incomplete"),
    (b"data: " + b"x" * (probe._MAX_BYTES + 1) + b"\n\n", "mcp_catalog_response_too_large"),
    (b"x-invalid\n\n", "mcp_catalog_sse_invalid_frame"),
])
def test_sse_rejects_malformed_or_unbounded_replies(
    monkeypatch: pytest.MonkeyPatch, stream: bytes, reason: str,
) -> None:
    install(monkeypatch, [stream])
    found = probe.probe_chatgpt_mcp_tool_catalog("https://mcp.example.org/mcp")
    assert found["ok"] is False
    assert found["reason"] == reason


def test_sse_does_not_use_unrelated_id_as_result(monkeypatch: pytest.MonkeyPatch) -> None:
    body = event(b'{"jsonrpc":"2.0","id":100,"result":{}}') + event(result(1, list(REQUIRED_CHATGPT_TURN_TOOLS)))
    install(monkeypatch, [body])
    found = probe.probe_chatgpt_mcp_tool_catalog("https://mcp.example.org/mcp")
    assert found["reason"] == "mcp_catalog_sse_wrong_request_id"
