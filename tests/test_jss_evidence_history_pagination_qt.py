"""Synthetic Qt pagination contracts, not runtime/operator acceptance."""
import json
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
pytest.importorskip("PySide6")
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication

from tools.jazn_run_studio.test_history_view import TestHistoryPanel


def make_run(count=601, *, unsealed=False):
    source = {"version":"synthetic-paging", "git_sha":None, "git_dirty":None}
    rows, files = [], {}
    for index in range(count):
        case_id = f"case-{index:04d}"
        row = {"scenario_id":case_id, "name":f"Case {index:04d}", "execution_status":"NOT_RUN",
               "full_gate_status":"NOT_RUN", "reason":"Synthetic view fixture; no test executed", "artifacts":[]}
        rows.append(row)
        files["scenarios/"+case_id+".txt"] = (row["name"]+"\nNOT_RUN\n").encode()
        files["results/"+case_id+".json"] = json.dumps(row).encode()
    summary = {"source":source,"run_id":"run-"+"0"*32,"saved_utc":"2026-11-01T00:00:00Z",
               "snapshot":"snapshot-"+"1"*32}
    if unsealed:
        summary["receipt_recovery"] = "UNSEALED"
    return {"summary":summary,"results":rows,"files":files}


@pytest.fixture
def panel(tmp_path, monkeypatch):
    monkeypatch.setenv("JAZN_OPERATOR_STATE_ROOT", str(tmp_path / "operator"))
    monkeypatch.setenv("JAZN_RUNTIME_WORKSPACE_DIR", str(tmp_path / "runtime"))
    app = QApplication.instance() or QApplication([])
    assert isinstance(app, QApplication)
    previous_font = app.font()
    font_id = -1
    font = Path("C:/Windows/Fonts/segoeui.ttf")
    if font.is_file():
        font_id = QFontDatabase.addApplicationFont(str(font))
        app.setFont(QFont("Segoe UI", 10))
    root = tmp_path / "SYSTEM"
    root.mkdir()
    widget = TestHistoryPanel(root)
    widget.loaded({"runs":[make_run()],"errors":[],"sha":None,"dirty":None,"base":tmp_path})
    yield app, widget
    widget.close()
    widget.deleteLater()
    app.processEvents()
    app.setFont(previous_font)
    if font_id >= 0:
        QFontDatabase.removeApplicationFont(font_id)


def test_all_scenarios_are_accessible_in_bounded_pages(panel):
    _, widget = panel
    assert len(widget.visible) == 300 and widget.visible[0]["scenario_id"] == "case-0000"
    assert not widget.previous_page_button.isEnabled()
    widget.next_page_button.click()
    assert len(widget.visible) == 300 and widget.visible[0]["scenario_id"] == "case-0300"
    widget.next_page_button.click()
    assert len(widget.visible) == 1 and widget.visible[0]["scenario_id"] == "case-0600"
    assert widget.page_counter.text() == "Strona 3 z 3"
    assert not widget.next_page_button.isEnabled()
    assert "Case 0600" in widget.details.toPlainText()
    widget.previous_page_button.click()
    assert widget.visible[0]["scenario_id"] == "case-0300"


def test_filters_reset_page_and_apply_to_the_entire_run(panel):
    _, widget = panel
    widget.next_page_button.click()
    widget.query.setText("Case 0600")
    assert widget.page_counter.text() == "Strona 1 z 1"
    assert widget.visible[0]["scenario_id"] == "case-0600"
    assert not widget.next_page_button.isEnabled() and not widget.previous_page_button.isEnabled()
    widget.query.setText("not-present")
    assert widget.table.rowCount() == 0 and widget.page_counter.text() == "Strona 0 z 0"
    widget.query.clear()
    assert widget.visible[0]["scenario_id"] == "case-0000"
    widget.status.setCurrentText("FAIL")
    assert widget.table.rowCount() == 0


def test_pagination_fits_compact_viewport(panel):
    app, widget = panel
    widget.resize(860, 580)
    widget.show()
    app.processEvents()
    assert widget.width() == 860 and widget.height() == 580
    assert widget.next_page_button.isVisible()


def test_failed_import_does_not_enable_export_of_an_unsealed_projection(panel, tmp_path):
    _, widget = panel
    widget.loaded({"runs":[make_run(unsealed=True)],"errors":[],"sha":None,"dirty":None,"base":tmp_path})
    assert not widget.export_button.isEnabled()
    widget.archive_completed({"error":"Synthetic rejected archive"})
    assert not widget.export_button.isEnabled()
