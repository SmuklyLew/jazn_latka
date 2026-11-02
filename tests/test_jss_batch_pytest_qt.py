"""Batch pytest in native JSS is explicit, cancellable, and distinct from TPA."""
from __future__ import annotations

from pathlib import Path
import os
import sys
import threading

import pytest

from tools.jazn_tests_studio import runner


def test_batch_evidence_uses_operator_state_and_exact_interpreter(tmp_path, monkeypatch):
    state = tmp_path / "operator-state"
    monkeypatch.setattr(runner, "state_dir", lambda _root: state)
    run = runner.PytestRun(tmp_path, python=sys.executable, evidence=True)
    assert not state.exists()
    run._prepare_evidence()
    assert run.evidence_dir is not None
    assert run.evidence_dir.parent == state / "batch-evidence"
    cmd = run.command()
    assert cmd[0] == sys.executable
    assert "-p" in cmd and "tools.jazn_run_studio.test_evidence_plugin" in cmd
    assert "--junitxml=" + str(run.evidence_dir / "junit.xml") in cmd
    assert cmd[-2:] == ["tests", "--ignore=tests/archive"]
    assert not (tmp_path / "tests").exists()


def test_batch_evidence_rejects_symlink(tmp_path, monkeypatch):
    if not hasattr(os, "symlink"):
        pytest.skip("No symlink support")
    state = tmp_path / "operator"
    state.mkdir()
    target = tmp_path / "external"
    target.mkdir()
    (state / "batch-evidence").symlink_to(target, target_is_directory=True)
    monkeypatch.setattr(runner, "state_dir", lambda _root: state)
    with pytest.raises(ValueError, match="Symlink"):
        runner.PytestRun(tmp_path, evidence=True)._prepare_evidence()
    assert list(target.iterdir()) == []


def test_native_batch_status_does_not_approve_real_acceptance(tmp_path, monkeypatch):
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication, QMessageBox
    from tools.jazn_run_studio import test_catalog_view as view

    if os.name != "nt" and not os.environ.get("DISPLAY"):
        monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])

    launched = []
    class FakeRun:
        def __init__(self, root, *, timeout, python, evidence, on_event):
            self.root = root
            self.timeout = timeout
            self.python = python
            self.evidence = evidence
            self.on_event = on_event
            self.done = threading.Event()
            self.result = None
            self.stopped = False
            launched.append(self)

        def start(self):
            return self

        def stop(self):
            self.stopped = True
            self.done.set()

    monkeypatch.setattr(view, "PytestRun", FakeRun)
    monkeypatch.setattr(QMessageBox, "question", lambda *_args: QMessageBox.StandardButton.Yes)
    widget = view.TestCatalogPanel(tmp_path, python=sys.executable)
    try:
        tpa_events = []
        widget.open_tpa_requested.connect(lambda: tpa_events.append(True))
        widget.tpa_button.click()
        assert tpa_events == [True]
        widget.run_all_button.click()
        assert len(launched) == 1
        run = launched[0]
        assert run.evidence is True and run.timeout == 7200 and run.python == sys.executable
        assert not widget.run_all_button.isEnabled()
        run.on_event({"type": "collection", "total": 3})
        run.on_event({"type": "result", "completed": 1, "total": 3, "status": "PASSED"})
        widget.poll_batch()
        assert widget.batch_progress.maximum() == 3
        assert widget.batch_progress.value() == 1
        run.result = {
            "ok": True, "outcome": "passed", "completed": 3, "total": 3,
            "counts": {"PASSED": 2, "SKIPPED": 1, "FAILED": 0, "ERROR": 0},
            "evidence_dir": str(tmp_path / "owned-evidence"),
        }
        run.done.set()
        widget.poll_batch()
        assert widget.run_all_button.isEnabled()
        assert "SKIPPED=1" in widget.batch_status.text()
        assert "NOT_RUN" in widget.batch_status.text()
        assert widget.shutdown() is True
    finally:
        widget.close()
        app.processEvents()


def test_native_batch_shutdown_stops_child_without_approving(tmp_path, monkeypatch):
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication, QMessageBox
    from tools.jazn_run_studio import test_catalog_view as view

    if os.name != "nt" and not os.environ.get("DISPLAY"):
        monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])

    class FakeRun:
        def __init__(self, *_args, **_kwargs):
            self.done = threading.Event()
        def start(self):
            return self
        def stop(self):
            self.done.set()
    monkeypatch.setattr(view, "PytestRun", FakeRun)
    monkeypatch.setattr(QMessageBox, "question", lambda *_a: QMessageBox.StandardButton.Yes)
    widget = view.TestCatalogPanel(tmp_path)
    try:
        widget.run_all_button.click()
        assert widget.shutdown() is False
        assert widget.shutdown() is True
    finally:
        widget.close()
        app.processEvents()
