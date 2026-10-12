from __future__ import annotations

from email.message import Message
from io import BytesIO
import json
from pathlib import Path
from typing import Callable, cast
import urllib.error
import urllib.request

import pytest

from latka_jazn import cli
from latka_jazn.mcp import ingress_diagnostics


class FakeResponse(BytesIO):
    def __init__(self, data: bytes, content_type: str = "application/json") -> None:
        super().__init__(data)
        self.status = 200
        self.headers = {"Content-Type": content_type}


def rpc_response(result: dict[str, object]) -> FakeResponse:
    return FakeResponse(json.dumps({"jsonrpc": "2.0", "id": 1, "result": result}).encode("utf-8"))


def _mock_transport(
    monkeypatch: pytest.MonkeyPatch,
    action: Callable[[urllib.request.Request], FakeResponse],
) -> list[urllib.request.Request]:
    calls: list[urllib.request.Request] = []

    class Opener:
        def open(self, request: urllib.request.Request, *, timeout: float) -> FakeResponse:
            assert timeout > 0
            calls.append(request)
            return action(request)

    def factory(*handlers: object) -> Opener:
        assert any(isinstance(h, ingress_diagnostics._RejectRedirects) for h in handlers)
        return Opener()

    monkeypatch.setattr(ingress_diagnostics.urllib.request, "build_opener", factory)
    return calls


def http_error(code: int, body: dict[str, object] | None = None) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        "https://mcp.example.org/mcp", code, "probe", Message(),
        BytesIO(json.dumps(body).encode("utf-8") if body is not None else b""),
    )


def _method(req: urllib.request.Request) -> str:
    return str(json.loads(cast(bytes, req.data))["method"])


def test_probe_rejects_public_plain_http_without_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("network access forbidden")
    monkeypatch.setattr(ingress_diagnostics.urllib.request, "build_opener", forbidden)
    result = ingress_diagnostics.probe_mcp_endpoint("http://public.example.org/mcp")
    assert result["reason"] == "mcp_probe_public_endpoint_requires_https"
    assert result["ok"] is False


def test_probe_modern_discover_request_mirrors_version_and_method(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def modern(req: urllib.request.Request) -> FakeResponse:
        body = json.loads(cast(bytes, req.data))
        assert req.get_method() == "POST"
        assert req.get_header("Mcp-protocol-version") == "2026-07-28"
        assert req.get_header("Mcp-method") == "server/discover"
        assert body["method"] == "server/discover"
        assert body["params"]["_meta"] == {
            "io.modelcontextprotocol/protocolVersion": "2026-07-28",
            "io.modelcontextprotocol/clientInfo": {
                "name": "jazn-mcp-preflight", "version": "1",
            },
            "io.modelcontextprotocol/clientCapabilities": {},
        }
        assert "message" not in str(body)
        return rpc_response({
            "resultType": "complete",
            "supportedVersions": ["2026-07-28"],
            "capabilities": {"tools": {}},
        })

    calls = _mock_transport(monkeypatch, modern)
    result = ingress_diagnostics.probe_mcp_endpoint("http://127.0.0.1:8788/mcp")
    assert len(calls) == 1
    assert result["ok"] is True
    assert result["mcp_discovery_verified"] is True
    assert result["mcp_initialize_verified"] is False
    assert result["protocol_era"] == "modern"
    assert result["legacy_fallback_used"] is False
    assert result["toolset_verified"] is False
    assert result["chatgpt_tools_exposed"] is None
    assert result["accepted_visible_turn"] is False


def test_probe_rejects_fake_modern_result_without_supported_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _mock_transport(monkeypatch, lambda req: rpc_response({
        "resultType": "complete", "supportedVersions": ["2025-11-25"],
        "capabilities": {"tools": {}},
    }))
    result = ingress_diagnostics.probe_mcp_endpoint("https://mcp.example.org/mcp")
    assert not result["ok"]
    assert not result["mcp_discovery_verified"]
    assert result["reason"] == "mcp_discovery_response_not_modern"
    assert len(calls) == 1


def test_probe_downgrades_to_legacy_only_after_unrecognized_http_4xx(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def legacy(req: urllib.request.Request) -> FakeResponse:
        body = json.loads(cast(bytes, req.data))
        if _method(req) == "server/discover":
            raise http_error(404)
        assert body["method"] == "initialize"
        assert body["params"]["protocolVersion"] == "2025-11-25"
        assert req.get_header("Mcp-protocol-version") is None
        return rpc_response({"capabilities": {"tools": {}}})

    calls = _mock_transport(monkeypatch, legacy)
    result = ingress_diagnostics.probe_mcp_endpoint("https://mcp.example.org/mcp")
    assert [_method(req) for req in calls] == ["server/discover", "initialize"]
    assert result["ok"] is True
    assert result["mcp_initialize_verified"] is True
    assert result["mcp_discovery_verified"] is False
    assert result["protocol_era"] == "legacy"
    assert result["legacy_fallback_used"] is True
    assert result["toolset_verified"] is False


def test_probe_detects_port_used_by_other_service(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing(req: urllib.request.Request) -> FakeResponse:
        raise http_error(404)
    calls = _mock_transport(monkeypatch, missing)
    result = ingress_diagnostics.probe_mcp_endpoint("http://127.0.0.1:8080/mcp")
    assert result["reason"] == "mcp_path_missing_or_wrong_service"
    assert result["http_status"] == 404
    assert result["toolset_verified"] is False
    assert len(calls) == 2


@pytest.mark.parametrize("status,reason", [
    (401, "mcp_authentication_required"),
    (403, "mcp_access_forbidden"),
    (429, "mcp_rate_limited"),
])
def test_probe_does_not_downgrade_auth_or_rate_limit(
    monkeypatch: pytest.MonkeyPatch, status: int, reason: str,
) -> None:
    def blocked(req: urllib.request.Request) -> FakeResponse:
        raise http_error(status)
    calls = _mock_transport(monkeypatch, blocked)
    result = ingress_diagnostics.probe_mcp_endpoint("https://mcp.example.org/mcp")
    assert result["reason"] == reason
    assert result["legacy_fallback_used"] is False
    assert result["mcp_initialize_verified"] is False
    assert len(calls) == 1


@pytest.mark.parametrize("error_code", [-32020, -32022, -32601])
def test_probe_does_not_downgrade_recognized_modern_protocol_error(
    monkeypatch: pytest.MonkeyPatch, error_code: int,
) -> None:
    def rejected(req: urllib.request.Request) -> FakeResponse:
        raise http_error(400, {"jsonrpc": "2.0", "id": 1, "error": {
            "code": error_code, "message": "protocol error",
        }})
    calls = _mock_transport(monkeypatch, rejected)
    result = ingress_diagnostics.probe_mcp_endpoint("https://mcp.example.org/mcp")
    assert result["reason"] == "mcp_modern_protocol_error"
    assert result["legacy_fallback_used"] is False
    assert len(calls) == 1


@pytest.mark.parametrize("status", [301, 302, 307, 308])
def test_probe_never_follows_http_redirect(
    monkeypatch: pytest.MonkeyPatch, status: int,
) -> None:
    redirect = ingress_diagnostics._RejectRedirects()
    assert redirect.redirect_request(
        urllib.request.Request("https://mcp.example.org/mcp", data=b"{}"),
        None, status, "redirect", Message(), "http://other.example/mcp",
    ) is None

    def moved(req: urllib.request.Request) -> FakeResponse:
        raise http_error(status)
    calls = _mock_transport(monkeypatch, moved)
    result = ingress_diagnostics.probe_mcp_endpoint("https://mcp.example.org/mcp")
    assert result["reason"] == "mcp_http_redirect_rejected"
    assert result["legacy_fallback_used"] is False
    assert len(calls) == 1


def test_probe_sse_remains_unverified(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_transport(monkeypatch, lambda req: FakeResponse(b"event: message", "text/event-stream"))
    result = ingress_diagnostics.probe_mcp_endpoint("http://localhost:8788/mcp")
    assert result["reason"] == "mcp_sse_requires_protocol_inspector"
    assert result["ok"] is False
    assert result["mcp_discovery_verified"] is False


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
