"""Manual evidence I/O stays durable and off Qt; fixtures never attest a human PASS."""
from copy import deepcopy
from pathlib import Path
import sys
import threading
import time

import pytest

pytest.importorskip("PySide6")
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QFileDialog

from tools.jazn_run_studio.tpa_reports import utc
from tools.jazn_run_studio.tpa_view import TPAPanel


@pytest.fixture
def manual_panel(tmp_path, monkeypatch):
    root = tmp_path / "SYSTEM"
    (root / "latka_jazn").mkdir(parents=True)
    (root / "latka_jazn/version.py").write_text('PACKAGE_VERSION="1.2.3"\n', encoding="utf-8")
    monkeypatch.setenv("JAZN_OPERATOR_STATE_ROOT", str(tmp_path / "operator"))
    monkeypatch.setenv("JAZN_RUNTIME_WORKSPACE_DIR", str(tmp_path / "runtime"))
    app = QApplication.instance() or QApplication([])
    panel = TPAPanel(root, python=sys.executable)
    report = panel.runner.store.create(("chat-resume",), "synthetic-python", {})
    report["results"][0].update(status="BLOCKED", reason="Synthetic fixture; no live test executed")
    report["finished_utc"] = utc()
    panel.runner.store.save(report)
    panel.report = report
    panel._history = [report]
    panel.history_mode = True
    panel.table.setCurrentCell(next(i for i,row in enumerate(panel.rows) if row['id']=='chat-resume'),0)
    panel.refresh_view()
    yield app, panel, report
    panel.close()
    panel.deleteLater()
    app.processEvents()


@pytest.mark.parametrize("operation", ["observation", "attachment"])
@pytest.mark.parametrize("fail", [False, True])
def test_manual_commit_is_background_and_adopted_only_after_ack(manual_panel, tmp_path, monkeypatch, operation, fail):
    app, panel, report = manual_panel
    store = panel.runner.store
    before = deepcopy(report)
    held_row = report["results"][0]
    entered, release = threading.Event(), threading.Event()
    writer_threads = []
    original_save = store.save
    def held_save(candidate):
        writer_threads.append(threading.get_ident())
        assert candidate is not report
        entered.set()
        if not release.wait(5):
            raise RuntimeError("Synthetic held write exceeded test deadline")
        if fail:
            raise OSError("Synthetic disk refusal")
        original_save(candidate)
    monkeypatch.setattr(store, "save", held_save)
    proof = tmp_path / "synthetic-proof.txt"
    proof.write_text("Synthetic test attachment; no human acceptance", encoding="utf-8")
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args, **kwargs: (str(proof), ""))
    ticks = []
    timer = QTimer(panel)
    timer.setInterval(10)
    timer.timeout.connect(lambda: ticks.append(time.monotonic()))
    timer.start()
    try:
        if operation == "attachment":
            panel.attach_proof()
        else:
            panel.finish_observation({"report":report,"key":"chat-resume","checked":[],
                "note":"Synthetic FAIL observation; no real operator acceptance", "proofs":[],"outcome":"FAIL"}, None)
        deadline = time.monotonic() + 3
        while (not entered.is_set() or len(ticks) < 3) and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.005)
        assert entered.is_set() and len(ticks) >= 3
        assert panel.manual_io.pending
        assert all(value != threading.get_ident() for value in writer_threads)
        assert report == before
        assert store.load(report["run_id"])["artifacts"] == before["artifacts"]
        assert not panel.observe_button.isEnabled() and not panel.proof_button.isEnabled()
        assert panel.shutdown() is False
    finally:
        release.set()
        deadline = time.monotonic() + 5
        while getattr(panel, "manual_io", None) is not None and panel.manual_io.pending and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.005)
        timer.stop()
    assert not panel.manual_io.pending
    assert report["results"][0] is held_row
    assert panel.observe_button.isEnabled() and panel.proof_button.isEnabled()
    if fail:
        assert report == before and store.load(report["run_id"])["artifacts"] == before["artifacts"]
        assert "OSError" in panel.feedback.text()
        assert not panel.attached
    elif operation == "attachment":
        assert len(report["artifacts"]) == 1
        assert panel.attached["chat-resume"] == report["artifacts"]
        assert store.load(report["run_id"])["artifacts"] == report["artifacts"]
    else:
        assert held_row["full_gate"] == "FAIL"
        assert store.load(report["run_id"])["results"][0]["full_gate"] == "FAIL"
        assert len(report["observations"]) == 1
