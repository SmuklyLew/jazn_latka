"""Stage 05: instance-bound admission is checked at the owning daemon."""
from __future__ import annotations

from io import StringIO
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from latka_jazn.config import JaznConfig
from latka_jazn.core import chat_command_contract as bridge, runtime_daemon as daemon
from latka_jazn.core import daemon_conversation_session as session


@pytest.mark.parametrize("pin", ["original", "", None, 123, "bad pin"])
def test_replacement_daemon_refuses_pinned_submit_before_job_lookup(
    monkeypatch: pytest.MonkeyPatch, pin: object,
) -> None:
    handler = object.__new__(daemon.JaznDaemonHandler)
    server = SimpleNamespace(daemon_instance_id="replacement",
                             submit_chat_job=lambda **_k: pytest.fail("must not admit"))
    monkeypatch.setattr(daemon.JaznDaemonHandler, "_daemon_server", lambda _self: server)
    job, created, error = handler._submit_chat_job_from_payload({
        "message": "synthetic", "request_id": "r", "expected_daemon_instance_id": pin,
    })
    assert job is None and created is False and error is not None
    assert error["error_code"] == ("daemon_instance_mismatch" if pin == "original"
                                   else "invalid_expected_daemon_instance")
    assert error["must_not_resubmit_user_message"] is True


def test_matching_pin_admits_once(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []
    handler = object.__new__(daemon.JaznDaemonHandler)
    def submit(**kwargs: Any) -> tuple[None, bool, None]:
        calls.append(kwargs)
        return None, True, None
    server = SimpleNamespace(daemon_instance_id="original", submit_chat_job=submit)
    monkeypatch.setattr(daemon.JaznDaemonHandler, "_daemon_server", lambda _self: server)
    handler._submit_chat_job_from_payload({"message": "synthetic", "request_id": "r",
                                          "expected_daemon_instance_id": "original"})
    assert len(calls) == 1
    assert calls[0]["request_id"] == "r"


@pytest.mark.parametrize("changed", ["none", "submit_instance", "submit_missing", "poll_instance", "poll_request"])
def test_pinned_chat_transport_does_not_accept_replacement_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, changed: str,
) -> None:
    calls: list[tuple[str, str, Any]] = []
    def http(method: str, url: str, payload: Any = None, **_k: Any) -> dict[str, Any]:
        calls.append((method, url, payload))
        response: dict[str, Any] = {"accepted": True, "request_id": "r", "daemon_instance_id": "original",
                                    "done": method == "GET", "phase_result_ready": False,
                                    "job_status": "completed" if method == "GET" else "queued",
                                    "result": {"ok": True, "synthetic": "final"}}
        if method == "POST" and changed == "submit_instance":
            response["daemon_instance_id"] = "replacement"
        if method == "POST" and changed == "submit_missing":
            response.pop("daemon_instance_id")
        if method == "GET" and changed == "poll_instance":
            response["daemon_instance_id"] = "replacement"
        if method == "GET" and changed == "poll_request":
            response["request_id"] = "other"
        return response
    monkeypatch.setattr(daemon, "http_json", http)
    monkeypatch.setattr(daemon, "read_daemon_auth_token", lambda _root: "synthetic")
    result = daemon.chat_daemon(JaznConfig(root=tmp_path), "synthetic", request_id="r",
                               expected_daemon_instance_id="original", timeout=1, poll_interval=0.02)
    assert calls[0][0] == "POST"
    assert calls[0][2]["expected_daemon_instance_id"] == "original"
    assert sum(method == "POST" for method, _, _ in calls) == 1
    if changed == "none":
        assert result["ok"] is True
        assert result["synthetic"] == "final"
    else:
        assert result["ok"] is False
        assert result["must_not_resubmit_user_message"] is True
        assert "synthetic" not in result


@pytest.mark.parametrize("pin", ["original", "", None])
def test_jsonl_forwards_explicit_pin_or_refuses_malformed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, pin: str | None,
) -> None:
    calls: list[dict[str, Any]] = []
    def fake(_cfg: JaznConfig, _text: str, **kwargs: Any) -> dict[str, Any]:
        calls.append(kwargs)
        return {"ok": False, "error_code": "synthetic"}
    monkeypatch.setattr(session, "chat_daemon", fake)
    out = StringIO()
    code = bridge.run_jsonl_chat_bridge(config=JaznConfig(root=tmp_path),
        session_id="s", no_carryover=False, command="--chat-ollama",
        stdin=StringIO(json.dumps({"message": "synthetic", "request_id": "r",
                                   "expected_daemon_instance_id": pin}) + "\n"),
        stdout=out, daemon_bound=True)
    assert code == 0
    result = json.loads(out.getvalue())
    if pin == "original":
        assert len(calls) == 1 and calls[0]["expected_daemon_instance_id"] == pin
    else:
        assert calls == []
        assert result["error_code"] == "invalid_expected_daemon_instance"
