"""Contract: read-only service polling preserves only fresh evidence and reports issues."""
from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from tools.jazn_run_studio import probes
from tools.jazn_run_studio.core import (
    Controller, OLLAMA_GENERATION_PROOF_SECONDS, Settings, retain_ollama_generation,
)
from tools.jazn_run_studio.service_status_dialog import assess_service
from tools.jazn_run_studio.window import Window


def _ollama(model: str = "gemma3:latest") -> dict:
    return {
        "service": "ollama", "endpoint_reachable": True,
        "models": [model], "selected_model": model,
        "selected_model_present": True, "generation_verified": False,
        "accepted_visible_turn": False,
    }


@pytest.fixture
def window(tmp_path: Path):
    app = QApplication.instance() or QApplication([])
    (tmp_path / "latka_jazn").mkdir()
    (tmp_path / "latka_jazn" / "version.py").touch()
    (tmp_path / "run.py").touch()
    (tmp_path / "main.py").touch()
    core = Controller(tmp_path, Settings(model="gemma3:latest", theme="dark"))
    widget = Window(core, smoke=True)
    yield widget
    widget.close()
    app.processEvents()


def test_generation_evidence_remains_green_across_passive_polls_but_expires():
    evidence = _ollama()
    now = 1000.0
    proof = ("gemma3:latest", now)
    merged = retain_ollama_generation(evidence, proof, now + 30.0)
    assert merged["generation_verified"] is True
    assert assess_service("ollama", merged, age_seconds=15)[0] == "good"
    assert assess_service(
        "ollama", merged, age_seconds=OLLAMA_GENERATION_PROOF_SECONDS
    )[0] == "warn"
    assert retain_ollama_generation(
        evidence, proof, now + OLLAMA_GENERATION_PROOF_SECONDS + 1.0
    )["generation_verified"] is False
    other = {**evidence, "selected_model": "different"}
    assert retain_ollama_generation(other, proof, now + 30)["generation_verified"] is False
    offline = {**evidence, "endpoint_reachable": False}
    assert retain_ollama_generation(offline, proof, now + 30)["generation_verified"] is False


def test_live_passive_probe_preserves_proof_without_generating(window, monkeypatch):
    core = window.core
    calls = {"generations": 0}

    def generation(model: str) -> dict:
        calls["generations"] += 1
        return {**_ollama(model), "generation_verified": True}

    monkeypatch.setattr(probes, "ollama_generation", generation)
    monkeypatch.setattr(probes, "ollama", _ollama)

    first = core.probe("ollama_generate")
    assert first.done.wait(5)
    assert first.state == "succeeded"
    monitor = core.probe("ollama", observe_only=True)
    assert monitor.done.wait(5)
    assert monitor.state == "succeeded"
    with core.lock:
        observed = [event[2] for event in list(core.events.queue)
                    if event[0] == "probe:ollama" and event[1] == "probe"]
    assert observed[-1]["generation_verified"] is True
    assert observed[-1]["monitor_only"] is True
    assert calls["generations"] == 1

    core.settings = Settings(model="other", theme="dark")
    monitor_again = core.probe("ollama", observe_only=True)
    assert monitor_again.done.wait(5)
    with core.lock:
        observed = [event[2] for event in list(core.events.queue)
                    if event[0] == "probe:ollama" and event[1] == "probe"]
    assert observed[-1]["generation_verified"] is False
    assert calls["generations"] == 1


def test_offline_probe_creates_single_operator_problem_and_recovery(window, monkeypatch):
    core = window.core

    def offline(_model: str) -> dict:
        raise ConnectionRefusedError("simulated unreachable")

    monkeypatch.setattr(probes, "ollama", offline)
    for _ in range(2):
        job = core.probe("ollama", observe_only=True)
        assert job.done.wait(5)
        assert job.state == "succeeded"
    with core.lock:
        events = list(core.events.queue)
    issues = [(key, value) for key, kind, value in events
              if key == "monitor:ollama" and kind == "monitor_issue"]
    assert len(issues) == 1
    assert issues[0][1]["state"] == "warning"
    assert len(core.logs["monitor:ollama"]) == 1

    workspace = window.workspace
    workspace.observe("monitor:ollama", "monitor_issue", issues[0][1])
    assert "monitor:ollama" in workspace.warnings
    assert workspace.problems.topLevelItemCount() == 1
    assert "Problemy: 1" in workspace.problem_summary.text()

    monkeypatch.setattr(probes, "ollama", _ollama)
    job = core.probe("ollama", observe_only=True)
    assert job.done.wait(5)
    with core.lock:
        events = list(core.events.queue)
    recovered = [(key, value) for key, kind, value in events
                 if key == "monitor:ollama" and kind == "monitor_issue"]
    assert len(recovered) == 2
    assert recovered[-1][1]["state"] == "resolved"
    workspace.observe("monitor:ollama", "monitor_issue", recovered[-1][1])
    assert not workspace.warnings
    assert len(core.logs["monitor:ollama"]) == 2


def test_failed_supervisor_stays_visible_in_problems_and_output(window):
    core = window.core
    core._monitor_condition("supervisor", "process_exit:1")
    snapshot = {"key": "supervisor", "state": "failed", "error": "process_exit:1",
                "returncode": 1, "finished": time.time()}
    core.emit("supervisor", "state", snapshot)
    workspace = window.workspace
    workspace.observe("monitor:supervisor", "monitor_issue", {
        "state": "warning", "error": "process_exit:1", "observed_at": time.time(),
    })
    workspace.observe("supervisor", "state", snapshot)
    assert "supervisor" in workspace.failures
    assert "monitor:supervisor" in workspace.warnings
    assert workspace.problems.topLevelItemCount() == 2
    assert "process_exit:1" in " ".join(core.logs["supervisor"])
