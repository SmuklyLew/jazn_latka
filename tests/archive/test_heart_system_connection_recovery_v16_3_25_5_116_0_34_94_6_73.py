"""Regression contracts for the selected interpreter, resume and report truth."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess

import pytest

from tools.jazn_run_studio import core as studio_core
from tools.jazn_run_studio.core import Controller, Settings, StudioError, mcp_dependency_preflight


@pytest.fixture
def controller(tmp_path: Path) -> Controller:
    (tmp_path / "latka_jazn").mkdir()
    (tmp_path / "latka_jazn/version.py").write_text("# synthetic", encoding="utf-8")
    (tmp_path / "main.py").touch()
    (tmp_path / "run.py").touch()
    return Controller(tmp_path, Settings(model="local-test"))


def test_mcp_imports_use_exact_gateway_interpreter(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(argv, **_kwargs):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, json.dumps({
            "mcp": {"import_ok": True, "version": "2.2.0"},
            "uvicorn": {"import_ok": True, "version": "0.31.1"},
            "starlette": {"import_ok": True, "version": "0.48.0"},
            "pydantic": {"import_ok": False, "version": None},
            "packaging": {"import_ok": True, "version": "26.3"},
            "tzdata": {"import_ok": True, "version": "2026.6"},
        }).encode(), b"")

    monkeypatch.setattr(studio_core, "run_external", fake_run)
    checks = mcp_dependency_preflight("selected-mcp-python", tmp_path)
    assert calls[0][0:3] == ["selected-mcp-python", "-I", "-c"]
    assert checks["pydantic"] is False


def test_mcp_start_fails_before_job_reservation_when_dependencies_missing(
    controller: Controller, monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FreePort:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def settimeout(self, _value):
            return None

        def connect_ex(self, _address):
            return 1

    monkeypatch.setattr(studio_core.socket, "socket", lambda: FreePort())
    monkeypatch.setattr(studio_core, "mcp_dependency_preflight", lambda *_args: {
        "mcp": False, "uvicorn": False, "starlette": False, "pydantic": False,
    })
    with pytest.raises(StudioError, match="pydantic"):
        controller.start_service("gateway")
    assert "service:gateway" not in controller.jobs


def test_report_requires_gui_ack_for_accepted_turn(controller: Controller) -> None:
    report = controller.report()
    assert report["accepted_visible_turn"] is None
    assert report["accepted_visible_turn_evidence"] is None
    with pytest.raises(StudioError):
        controller.confirm_visible_turn({"request_id": "r"})
    controller.confirm_visible_turn({"request_id": "r", "turn_id": "t", "trace_id": "trace",
                                     "text": "never write me into the report"})
    report = controller.report()
    assert report["accepted_visible_turn"] is True
    assert report["accepted_visible_turn_evidence"]["basis"] == "gui_display_and_checkpoint_ack"
    assert "never write me" not in json.dumps(report)


def test_resume_nonzero_exit_preserves_request_and_error(controller: Controller, monkeypatch: pytest.MonkeyPatch) -> None:
    from tools.jazn_run_studio import chat as chat_module

    client = chat_module.ChatClient(controller)
    client.pending = "same-request"
    monkeypatch.setattr(client, "receive", lambda _payload: None)
    monkeypatch.setattr(chat_module, "run", lambda argv, **_kw:
                        subprocess.CompletedProcess(argv, 1, b'{"done":false}', b""))
    client.resume()
    assert controller.jobs["chat:resume"].done.wait(5)
    job = controller.jobs["chat:resume"]
    assert job.state == "failed" and job.error == "resume_exit:1"
    assert client.pending == "same-request"


def test_resume_pending_is_successful_poll_not_false_final(controller: Controller, monkeypatch: pytest.MonkeyPatch) -> None:
    from tools.jazn_run_studio import chat as chat_module

    client = chat_module.ChatClient(controller)
    client.pending = "same-request"
    monkeypatch.setattr(client, "receive", lambda _payload: None)
    monkeypatch.setattr(chat_module, "run", lambda argv, **_kw:
                        subprocess.CompletedProcess(argv, 0, b'{"done":false}', b""))
    client.resume()
    assert controller.jobs["chat:resume"].done.wait(5)
    assert controller.jobs["chat:resume"].state == "succeeded"
    assert client.pending == "same-request"
