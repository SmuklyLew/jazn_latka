from __future__ import annotations

from io import BytesIO
from email.message import Message
import urllib.request
import json
from pathlib import Path
import urllib.error

import pytest

from latka_jazn import cli
from latka_jazn.mcp import ingress_diagnostics


class FakeResponse(BytesIO):
    def __init__(self, data: bytes, content_type: str = "application/json") -> None:
        super().__init__(data)
        self.status = 200
        self.headers = {"Content-Type": content_type}


def test_probe_rejects_public_plain_http_without_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("network access forbidden")
    monkeypatch.setattr(ingress_diagnostics.urllib.request, "urlopen", forbidden)
    result = ingress_diagnostics.probe_mcp_endpoint("http://public.example.org/mcp")
    assert result["reason"] == "mcp_probe_public_endpoint_requires_https"
    assert result["ok"] is False


def test_probe_detects_port_used_by_other_service(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing(req: object, *, timeout: float) -> None:
        raise urllib.error.HTTPError("http://127.0.0.1:8080/mcp", 404, "missing", Message(), BytesIO())
    monkeypatch.setattr(ingress_diagnostics.urllib.request, "urlopen", missing)
    result = ingress_diagnostics.probe_mcp_endpoint("http://127.0.0.1:8080/mcp")
    assert result["reason"] == "mcp_path_missing_or_wrong_service"
    assert result["http_status"] == 404
    assert result["toolset_verified"] is False


def test_probe_does_not_treat_auth_challenge_as_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    def denied(req: object, *, timeout: float) -> None:
        raise urllib.error.HTTPError("https://mcp.example.org/mcp", 401, "auth", Message(), BytesIO())
    monkeypatch.setattr(ingress_diagnostics.urllib.request, "urlopen", denied)
    result = ingress_diagnostics.probe_mcp_endpoint("https://mcp.example.org/mcp")
    assert result["reason"] == "mcp_authentication_required"
    assert result["mcp_initialize_verified"] is False


def test_probe_validates_initialize_but_not_tool_exposure(monkeypatch: pytest.MonkeyPatch) -> None:
    def working(req: urllib.request.Request, *, timeout: float) -> FakeResponse:
        body = json.loads(req.data)
        assert body["method"] == "initialize"
        assert "message" not in str(body)
        return FakeResponse(json.dumps({
            "jsonrpc": "2.0", "id": 1,
            "result": {"capabilities": {"tools": {}}}
        }).encode("utf-8"))
    monkeypatch.setattr(ingress_diagnostics.urllib.request, "urlopen", working)
    result = ingress_diagnostics.probe_mcp_endpoint("http://127.0.0.1:8788/mcp")
    assert result["mcp_initialize_verified"] is True
    assert result["toolset_verified"] is False
    assert result["chatgpt_tools_exposed"] is None


def test_probe_sse_does_not_fake_initialized_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        ingress_diagnostics.urllib.request, "urlopen",
        lambda req, timeout: FakeResponse(b"event: message", "text/event-stream"),
    )
    result = ingress_diagnostics.probe_mcp_endpoint("http://localhost:8788/mcp")
    assert result["reason"] == "mcp_sse_requires_protocol_inspector"
    assert result["ok"] is False


def test_cli_mcp_probe_exposes_machine_readable_diagnosis(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(ingress_diagnostics, "probe_mcp_endpoint",
                        lambda url, *, timeout: {"ok": False, "reason": "mcp_path_missing_or_wrong_service"})
    code = cli.main(["mcp-probe", "--root", str(tmp_path), "--json"])
    assert code == 1
    assert json.loads(capsys.readouterr().out)["reason"] == "mcp_path_missing_or_wrong_service"


def test_acknowledged_job_loss_is_diagnostic_not_replay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from latka_jazn.config import JaznConfig
    from latka_jazn.core import runtime_daemon

    monkeypatch.setattr(runtime_daemon, "chat_daemon_submit",
                        lambda *args, **kwargs: {
                            "accepted": True, "done": False,
                            "request_id": "accepted-request-1",
                            "job_status": "queued",
                        })
    seen: list[str] = []

    def missing(config: object, request_id: str, **kwargs: object) -> dict[str, object]:
        seen.append(request_id)
        return {
            "ok": False, "error_code": "chat_job_not_found",
            "request_id": request_id,
        }

    monkeypatch.setattr(runtime_daemon, "chat_daemon_result", missing)
    response = runtime_daemon.chat_daemon(
        JaznConfig(root=tmp_path), "Test message",
        session_id="test-session",
        request_id="accepted-request-1",
        timeout=0.2, poll_interval=0.02,
    )
    assert seen == ["accepted-request-1"]
    assert response["ok"] is False
    assert response["error_code"] == "chat_job_not_found"
    assert response["submit_acknowledged"] is True
    assert response["must_not_resubmit_user_message"] is True
    assert response["diagnostic_reason"] == "acknowledged_job_missing_from_daemon"
    assert response["submitted_request_id"] == "accepted-request-1"
