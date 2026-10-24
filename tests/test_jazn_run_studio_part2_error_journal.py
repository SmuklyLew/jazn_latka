"""Failure journal is bounded, structured and never stores raw chat data."""
from __future__ import annotations

import json

from latka_jazn.core.runtime_root import workspace_runtime_path
from tools.jazn_run_studio.core import Controller, Redactor, Settings, write_error_record


def test_failure_journal_redacts_secret_values(tmp_path):
    redactor = Redactor({"JAZN_TEST_SECRET": "s3cr3t-should-not-escape"})
    filename = write_error_record(tmp_path, "probe:gateway", {
        "error": "token=s3cr3t-should-not-escape",
        "returncode": 5,
    }, redactor)
    assert filename == workspace_runtime_path(tmp_path) / "jazn_run_studio" / "errors_jazn_studio.log"
    raw = filename.read_text(encoding="utf-8")
    assert "s3cr3t-should-not-escape" not in raw
    payload = json.loads(raw.splitlines()[-1])
    assert payload["state"] == "failed"
    assert payload["returncode"] == 5
    assert "[UKRYTO]" in payload["error"]
    assert "observed_at_utc" in payload


def test_journal_record_excludes_unrelated_sensitive_fields(tmp_path):
    output = write_error_record(tmp_path, "status", {
        "error": "timeout", "returncode": 1,
        "message": "private user dialogue",
        "argv": ["-m", "private-source"],
    }, Redactor({})).read_text(encoding="utf-8")
    assert "private user dialogue" not in output
    assert "private-source" not in output


def test_terminal_failed_event_still_emitted_if_error_disk_unavailable(tmp_path, monkeypatch):
    (tmp_path / "latka_jazn").mkdir()
    (tmp_path / "latka_jazn" / "version.py").touch()
    (tmp_path / "run.py").touch()
    (tmp_path / "main.py").touch()
    core = Controller(tmp_path, Settings())
    import tools.jazn_run_studio.core as module

    def failure(*_args):
        raise OSError("disk unavailable")

    monkeypatch.setattr(module, "write_error_record", failure)
    core.emit("probe:ollama", "state", {
        "state": "failed", "pid": None, "error": "service_not_ready",
    })
    assert core.critical_events.get_nowait()[0] == "studio:errors"
    key, kind, value = core.events.get_nowait()
    assert (key, kind, value["state"]) == ("probe:ollama", "state", "failed")
