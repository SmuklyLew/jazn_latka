"""Actual child pytest runs, event-loop responsiveness and honest terminal states."""
from pathlib import Path
import sys
import time
import pytest
pytest.importorskip("PySide6")
from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QApplication
from tools.jazn_run_studio.tpa_catalog import execution_map
from tools.jazn_run_studio.tpa_engine import TPARunner, readiness
from tools.jazn_run_studio.tpa_view import TPAPanel


@pytest.fixture
def system(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    root = tmp_path / "SYSTEM"
    (root / "latka_jazn").mkdir(parents=True)
    (root / "latka_jazn/version.py").write_text('PACKAGE_VERSION="1.2.3"\n', encoding="utf-8")
    monkeypatch.setenv("JAZN_OPERATOR_STATE_ROOT", str(tmp_path / "operator"))
    for case in execution_map():
        for name in case["files"]:
            file = root / name
            file.parent.mkdir(exist_ok=True, parents=True)
            file.write_text("def test_synthetic(): assert True\n", encoding="utf-8")
    yield root, app
    app.processEvents()


def wait_until(predicate, timeout=20):
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        # qWait's binding can retain the GIL across each wait and starve a
        # Python worker between filesystem calls. Match QApplication.exec:
        # pump Qt and release the GIL, keeping the same deadline/assertions.
        QApplication.processEvents()
        time.sleep(0.005)
    assert predicate(), "asynchronous operation did not complete"


def test_actual_selected_interpreter_preflight_and_partially_ready_set(system):
    root, _ = system
    runner = TPARunner(root, sys.executable)
    runner.check_ready()
    wait_until(lambda: not runner.active)
    assert runner.probe["ok"] and runner.probe["imports"]["pytest"]["ok"]
    probe = dict(runner.probe, imports={**runner.probe["imports"], "PySide6": {"ok": False}})
    checks = readiness(root, probe)
    assert checks["smoke-isolation"]["ready"]
    assert not checks["ui-accessibility"]["ready"]
    assert "PySide6" in checks["ui-accessibility"]["reason"]
    probe["imports"]["pytest"] = {"ok": False}
    assert all(not r["ready"] for r in readiness(root, probe).values())


@pytest.mark.parametrize("body,status", [
    ("assert True", "PASS"), ("assert False, 'observed failure'", "FAIL"),
    ("import pytest; pytest.skip('resource missing')", "SKIPPED"),
])
def test_real_pytest_result_persistence_and_junit(system, body, status):
    root, _ = system
    (root / "tests/test_package_smoke_workspace_isolation.py").write_text("def test_actual(): " + body + "\n", encoding="utf-8")
    runner = TPARunner(root, sys.executable)
    runner.start_selection(("smoke-isolation",))
    wait_until(lambda: not runner.active)
    assert runner.report is not None
    row = runner.report["results"][0]
    assert row["status"] == status
    assert row["full_gate"] == "NOT_RUN"
    loaded = runner.store.load(runner.report["run_id"])
    assert loaded["summary"]["counts"] == {status: 1}
    assert (runner.store.folder(loaded["run_id"]) / row["junit"]).is_file()
    assert not (root / "workspace_runtime").exists()


@pytest.mark.parametrize("cancel,expected", [(True, "CANCELLED"), (False, "TIMEOUT")])
def test_cancel_timeout_and_gui_responsiveness(system, cancel, expected):
    root, app = system
    (root / "tests/test_package_smoke_workspace_isolation.py").write_text("import time\ndef test_wait(): time.sleep(10)\n", encoding="utf-8")
    runner = TPARunner(root, sys.executable)
    runner.timeout_ms = 400
    beats = []
    timer = QTimer()
    timer.timeout.connect(lambda: beats.append(1))
    timer.start(20)
    runner.start_selection(("smoke-isolation", "config-persistence"))
    with pytest.raises(ValueError, match="nadal trwa"):
        runner.start_selection(("smoke-isolation",))
    wait_until(lambda: runner.phase == "tests")
    if cancel:
        runner.stop()
    wait_until(lambda: not runner.active)
    timer.stop()
    assert runner.report is not None
    assert runner.report["results"][0]["status"] == expected
    if cancel:
        assert runner.report["results"][1]["status"] == "CANCELLED"
    assert len(beats) > 3
    assert runner.process.processId() == 0


def test_invalid_python_is_durable_blocked_and_missing_files_do_not_abort_queue(system):
    root, _ = system
    runner = TPARunner(root, "")
    runner.start_selection(("smoke-isolation",))
    wait_until(lambda: not runner.active)
    assert runner.report is not None
    assert runner.report["results"][0]["status"] == "BLOCKED"
    runner.python = sys.executable
    (root / "tests/test_package_smoke_workspace_isolation.py").unlink()
    runner.start_selection(("smoke-isolation", "config-persistence"))
    wait_until(lambda: not runner.active)
    assert [r["status"] for r in runner.report["results"]] == ["BLOCKED", "PASS"]


def test_panel_preserves_selection_history_filters_and_routes_correct_log(system):
    root, app = system
    panel = TPAPanel(root, python=sys.executable)
    panel.resize(1000, 850)
    panel.show()
    panel.table.selectRow(5)
    selected = panel.chosen()
    panel.refresh()
    assert panel.chosen() == selected
    panel.search.setText("no such test")
    assert all(panel.table.isRowHidden(i) for i in range(22))
    panel.attempt(panel.run_selected_subcheck)
    assert "Zaznacz" in panel.feedback.text()
    panel.search.clear()
    panel.start((selected,))
    wait_until(lambda: not panel.runner.active)
    assert panel.report is not None
    run_id = panel.report["run_id"]
    panel.show_log()
    assert "test_synthetic" in panel.auto_log.toPlainText()
    assert panel.runner.store.load(run_id)["results"][0]["status"] == "PASS"
    panel.close()
    restored = TPAPanel(root, python=sys.executable)
    assert restored.report is not None
    assert restored.report["run_id"] == run_id
    restored.table.selectRow(0)
    restored.attempt(restored.show_log)
    assert "nie ma logu" in restored.feedback.text()
    restored.table.clearSelection()
    restored.table.setCurrentCell(-1, -1)
    restored.attempt(restored.show_log)
    assert "Wybierz" in restored.feedback.text()
    restored.close()


def test_main_window_problem_log_without_selection(window):
    window.workspace.show_selected_logs()
    assert "Najpierw wybierz" in window.workspace.problem_details.text()


def test_real_process_start_error_is_blocked_not_a_hanging_run(system):
    root, _ = system
    wrong_exe = root.parent / "invalid-python.exe"
    wrong_exe.write_text("not an executable", encoding="utf-8")
    runner = TPARunner(root, str(wrong_exe))
    runner.start_selection(("smoke-isolation",))
    wait_until(lambda: not runner.active)
    assert runner.report is not None
    assert runner.report["results"][0]["status"] == "BLOCKED"
    assert runner.process.processId() == 0


def test_panel_keeps_guide_draft_and_defers_close_until_owned_process_stops(system):
    root, _ = system
    panel = TPAPanel(root, python=sys.executable)
    panel.show()
    panel.table.selectRow(5)
    panel.note.setPlainText("Synthetic operator draft")
    panel.checklist.item(0).setCheckState(Qt.CheckState.Checked)
    panel.table.selectRow(6)
    panel.refresh()
    panel.table.selectRow(5)
    assert panel.note.toPlainText() == "Synthetic operator draft"
    assert panel.checklist.item(0).checkState() == Qt.CheckState.Checked
    (root / "tests/test_package_smoke_workspace_isolation.py").write_text("import time\ndef test_wait(): time.sleep(10)\n", encoding="utf-8")
    panel.start(("smoke-isolation",))
    wait_until(lambda: panel.runner.phase == "tests")
    panel.close()
    wait_until(lambda: not panel.runner.active and not panel.isVisible())
    assert panel.report is not None
    assert panel.report["results"][0]["status"] == "CANCELLED"


def test_report_write_failure_is_visible_and_never_silently_passes(system, monkeypatch):
    root, _ = system
    runner = TPARunner(root, sys.executable)
    runner.start_selection(("smoke-isolation",))
    def disk_full(report):
        raise OSError("synthetic disk full")
    monkeypatch.setattr(runner.store, "save", disk_full)
    wait_until(lambda: not runner.active)
    assert runner.report is not None
    assert "Nie zapisano raportu" in runner.report["persistence_error"]
    assert runner.report["results"][0]["status"] == "CANCELLED"


from tests.test_jazn_run_studio_layout import window
