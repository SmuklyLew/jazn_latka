from __future__ import annotations

from email.message import Message
from io import BytesIO
import json
from typing import Any, cast
import urllib.error
import urllib.request

import pytest

from latka_jazn import cli
from latka_jazn.mcp import chatgpt_bridge_probe as module
from latka_jazn.mcp.chatgpt_toolset import REQUIRED_CHATGPT_TURN_TOOLS


class FakeResponse(BytesIO):
    status = 200

    def __init__(self, value: Any, *, content_type: str = "application/json") -> None:
        super().__init__(json.dumps(value).encode("utf-8"))
        self.headers = {"Content-Type": content_type}


def good_tool(name: str) -> dict[str, Any]:
    return {
        "name": name, "description": "Read or process a Jaźń runtime turn",
        "inputSchema": {"type": "object", "properties": {}},
    }


def reply(items: list[dict[str, Any]], *, page: int = 1, cursor: str | None = None) -> FakeResponse:
    result: dict[str, Any] = {"resultType": "complete", "tools": items}
    if cursor is not None:
        result["nextCursor"] = cursor
    return FakeResponse({"jsonrpc": "2.0", "id": page, "result": result})


def setup(monkeypatch: pytest.MonkeyPatch, fn: Any) -> list[urllib.request.Request]:
    calls: list[urllib.request.Request] = []

    class Opener:
        def open(self, request: urllib.request.Request, *, timeout: float) -> FakeResponse:
            assert 0.1 <= timeout <= 30
            calls.append(request)
            return fn(request)

    def factory(*handlers: object) -> Opener:
        assert any(isinstance(h, module._RejectRedirects) for h in handlers)
        return Opener()

    monkeypatch.setattr(module.urllib.request, "build_opener", factory)
    return calls


def test_complete_catalog_is_not_chatgpt_host_exposure(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: urllib.request.Request) -> FakeResponse:
        assert request.get_method() == "POST"
        assert request.get_header("Mcp-method") == "tools/list"
        assert request.get_header("Mcp-protocol-version") == "2026-07-28"
        body = json.loads(cast(bytes, request.data))
        assert body["method"] == "tools/list"
        assert body["params"]["_meta"]["io.modelcontextprotocol/protocolVersion"] == "2026-07-28"
        return reply([good_tool(name) for name in REQUIRED_CHATGPT_TURN_TOOLS])

    calls = setup(monkeypatch, handler)
    result = module.probe_chatgpt_mcp_tool_catalog("http://localhost:8080/mcp")
    assert len(calls) == 1
    assert result["ok"] is True
    assert result["tool_catalog_verified"] is True
    assert result["missing_required_tool_names"] == []
    assert result["chatgpt_current_message_toolset_verified"] is False
    assert result["daemon_conversation_ready_verified"] is False
    assert result["accepted_visible_turn_verified"] is False


def test_catalog_handles_cursor_pagination_without_turn_submission(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: urllib.request.Request) -> FakeResponse:
        body = json.loads(cast(bytes, request.data))
        if body["id"] == 1:
            assert "cursor" not in body["params"]
            return reply([good_tool(REQUIRED_CHATGPT_TURN_TOOLS[0])], cursor="more")
        assert body["params"]["cursor"] == "more"
        return reply([good_tool(name) for name in REQUIRED_CHATGPT_TURN_TOOLS[1:]], page=2)

    calls = setup(monkeypatch, handler)
    result = module.probe_chatgpt_mcp_tool_catalog("https://mcp.example.org/mcp")
    assert result["ok"] is True
    assert result["pages_checked"] == 2
    assert len(calls) == 2
    assert all(json.loads(cast(bytes, call.data))["method"] == "tools/list" for call in calls)


def test_missing_tool_rejected_and_no_fabricated_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    setup(monkeypatch, lambda _: reply([good_tool(REQUIRED_CHATGPT_TURN_TOOLS[0])]))
    result = module.probe_chatgpt_mcp_tool_catalog("https://mcp.example.org/mcp")
    assert result["ok"] is False
    assert result["reason"] == "mcp_chatgpt_required_tools_missing"
    assert len(result["missing_required_tool_names"]) == 3


def test_missing_metadata_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    tools = [good_tool(name) for name in REQUIRED_CHATGPT_TURN_TOOLS]
    del tools[0]["inputSchema"]
    setup(monkeypatch, lambda _: reply(tools))
    assert module.probe_chatgpt_mcp_tool_catalog("https://mcp.example.org/mcp")["reason"] == "mcp_chatgpt_tool_metadata_invalid"


def test_non_rpc_response_is_not_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    setup(monkeypatch, lambda _: FakeResponse({"tools": [good_tool(name) for name in REQUIRED_CHATGPT_TURN_TOOLS]}))
    assert module.probe_chatgpt_mcp_tool_catalog("https://mcp.example.org/mcp")["ok"] is False


@pytest.mark.parametrize("status, reason", [
    (401, "mcp_catalog_auth_required"),
    (403, "mcp_catalog_forbidden"),
    (404, "mcp_catalog_endpoint_missing"),
    (429, "mcp_catalog_rate_limited"),
    (307, "mcp_catalog_redirect_rejected"),
])
def test_transport_errors_fail_closed(monkeypatch: pytest.MonkeyPatch, status: int, reason: str) -> None:
    def handler(_: urllib.request.Request) -> FakeResponse:
        raise urllib.error.HTTPError("https://example.org/mcp", status, "error", Message(), BytesIO(b""))

    setup(monkeypatch, handler)
    result = module.probe_chatgpt_mcp_tool_catalog("https://mcp.example.org/mcp")
    assert result["reason"] == reason
    assert result["ok"] is False


def test_token_is_sent_only_to_https_and_never_returned(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: urllib.request.Request) -> FakeResponse:
        assert request.get_header("Authorization") == "Bearer sensitive-test-token"
        return reply([good_tool(name) for name in REQUIRED_CHATGPT_TURN_TOOLS])

    calls = setup(monkeypatch, handler)
    rejected = module.probe_chatgpt_mcp_tool_catalog(
        "http://localhost:8080/mcp",
        token_env="JAZN_TEST_TOKEN",
        environ={"JAZN_TEST_TOKEN": "sensitive-test-token"},
    )
    assert rejected["reason"] == "mcp_catalog_bearer_requires_https"
    assert len(calls) == 0
    accepted = module.probe_chatgpt_mcp_tool_catalog(
        "https://mcp.example.org/mcp",
        token_env="JAZN_TEST_TOKEN",
        environ={"JAZN_TEST_TOKEN": "sensitive-test-token"},
    )
    assert accepted["ok"] is True
    assert "sensitive-test-token" not in json.dumps(accepted)
    assert len(calls) == 1


def test_bad_url_never_opens_connection(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*a: object, **k: object) -> None:
        raise AssertionError("no-network-on-invalid-url")

    monkeypatch.setattr(module.urllib.request, "build_opener", forbidden)
    result = module.probe_chatgpt_mcp_tool_catalog("http://public.example.org/mcp")
    assert result["ok"] is False
    assert result["reason"] == "mcp_probe_public_endpoint_requires_https"


def test_cli_uses_same_canonical_runpy_mcp_probe_dispatch(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(module, "probe_chatgpt_mcp_tool_catalog",
                        lambda url, *, timeout, token_env: {"ok": True, "reason": "mcp_chatgpt_tool_catalog_verified"})
    code = cli.main([
        "mcp-probe", "--root", str(tmp_path), "--url", "https://mcp.example.org/mcp",
        "--check-chatgpt-tool-catalog", "--json",
    ])
    assert code == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True
