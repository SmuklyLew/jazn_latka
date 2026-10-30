"""TPA live resume must confirm daemon admission before simulating lost transport."""
from __future__ import annotations

import json
from pathlib import Path
from subprocess import CompletedProcess
from types import SimpleNamespace

import pytest

from tools.jazn_run_studio import tpa_live


class _Client:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def resume_command(self, request_id: str) -> list[str]:
        self.calls.append(request_id)
        return ["python", "--daemon-result", request_id]


def _result(payload: dict, *, code: int = 0) -> CompletedProcess[bytes]:
    return CompletedProcess(["python"], code, json.dumps(payload).encode("utf-8"), b"")


def test_receipt_waits_for_daemon_job_without_replaying_user_text(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    request = "studio-turn-original"
    responses = iter([
        _result({"request_id": request, "error_code": "chat_job_not_found", "ok": False}, code=1),
        _result({"request_id": request, "accepted": True, "job_status": "queued", "done": False}),
    ])
    commands: list[list[str]] = []

    def fake_run(command: list[str], *, cwd: Path, timeout: float) -> CompletedProcess[bytes]:
        assert cwd == tmp_path
        commands.append(command)
        return next(responses)

    monkeypatch.setattr(tpa_live, "run_external", fake_run)
    monkeypatch.setattr(tpa_live.time, "sleep", lambda _: None)
    client = _Client()
    result = tpa_live.await_daemon_receipt(
        SimpleNamespace(root=tmp_path), client, request, lambda: None,
    )
    assert result == {"request_id": request, "job_status": "queued",
                      "confirmed": True, "probe_attempts": 2}
    assert client.calls == [request, request]
    assert commands == [["python", "--daemon-result", request]] * 2


def test_receipt_rejects_foreign_or_failed_request(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    client = _Client()
    for payload in (
        {"request_id": "foreign", "accepted": True, "job_status": "running"},
        {"request_id": "studio-turn-original", "accepted": True, "job_status": "failed"},
    ):
        monkeypatch.setattr(tpa_live, "run_external",
                            lambda *a, **kw: _result(payload))
        with pytest.raises(ValueError):
            tpa_live.await_daemon_receipt(
                SimpleNamespace(root=tmp_path), client, "studio-turn-original", lambda: None,
            )


def test_receipt_timeout_does_not_fake_admission(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    monkeypatch.setattr(tpa_live, "run_external", lambda *a, **kw: _result(
        {"request_id": "studio-turn-original", "error_code": "chat_job_not_found"},
        code=1,
    ))
    clock = iter([0.0, 0.5, 1.5, 2.5])
    monkeypatch.setattr(tpa_live.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(tpa_live.time, "sleep", lambda _: None)
    with pytest.raises(TimeoutError, match="nie potwierdził"):
        tpa_live.await_daemon_receipt(
            SimpleNamespace(root=tmp_path), _Client(), "studio-turn-original",
            lambda: None, timeout_seconds=2.0,
        )


@pytest.mark.parametrize(("outcome", "exit_code"), [
    ("PASS", 0), ("TIMEOUT", 1), ("FAIL", 1), ("BLOCKED", 1), ("CANCELLED", 1),
])
def test_live_cli_exit_code_matches_reported_status(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
    outcome: str, exit_code: int,
) -> None:
    monkeypatch.setattr(tpa_live, "validate_staging", lambda *args, **kwargs: tmp_path)
    monkeypatch.setattr(tpa_live, "exercise",
                        lambda *args, **kwargs: {"status": outcome, "reason": "synthetic"})
    monkeypatch.setattr(tpa_live.sys, "argv", [
        "tpa_live", "--root", str(tmp_path), "--folder", str(tmp_path),
        "--run-id", "run-synthetic", "--case", "chat-resume", "--model", "gemma3:latest",
    ])
    assert tpa_live.main() == exit_code
