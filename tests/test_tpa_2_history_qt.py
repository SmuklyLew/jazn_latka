"""Real Qt panel restart and explicit historical scope, using synthetic reports."""
import sys

import pytest
pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication

from tools.jazn_run_studio.tpa_view import TPAPanel
from tests.test_tpa_2_current_state import store, completed


def test_default_projection_and_history_are_separate_after_panel_restart(store):
    app = QApplication.instance() or QApplication([])
    first = completed(store)
    second = completed(store, "smoke-isolation")
    panel = TPAPanel(store.root, python=sys.executable)
    try:
        assert not panel.history_mode
        assert panel.cell(5, 1).text() == "PASS"
        assert panel.cell(6, 1).text() == "PASS"
        assert panel.cell(6, 3).text() == "NOT_RUN"
        assert "zbiorczy" in panel.summary.text()
        panel._load_report(second["run_id"])
        assert panel.history_mode
        assert panel.cell(6, 1).text() == "NOT_RUN"
        panel.show_current()
        assert panel.cell(6, 1).text() == "PASS"
        panel.table.selectRow(6)
        assert panel.report is not None
        assert panel.report["run_id"] == first["run_id"]
    finally:
        panel.close()
        app.processEvents()
    restored = TPAPanel(store.root, python=sys.executable)
    try:
        assert not restored.history_mode
        assert restored.cell(5, 1).text() == restored.cell(6, 1).text() == "PASS"
    finally:
        restored.close()
        app.processEvents()


def test_corrupt_report_is_recoverable_from_history_control(store):
    app = QApplication.instance() or QApplication([])
    report = completed(store)
    path = store.folder(report["run_id"]) / "report.json"
    path.write_bytes(b"{damaged")
    panel = TPAPanel(store.root, python=sys.executable)
    try:
        panel.history.setCurrentIndex(panel.history.findData(report["run_id"]))
        panel.recover_selected_report()
        assert store.load(report["run_id"])["results"][0]["status"] == "PASS"
        assert "Odzyskano" in panel.feedback.text()
        assert panel.cell(6, 1).text() == "PASS"
    finally:
        panel.close()
        app.processEvents()
