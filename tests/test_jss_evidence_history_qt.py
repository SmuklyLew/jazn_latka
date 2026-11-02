"""Real Qt widgets inspect immutable reports without starting runtime or tests."""
import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication

from tools.jazn_run_studio.test_history_view import TestHistoryPanel
from tools.jazn_run_studio.test_catalog_view import TestCatalogPanel
from tools.jazn_run_studio.tpa_reports import RunStore


@pytest.fixture
def setup_history(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    root = tmp_path / "SYSTEM"
    (root / "latka_jazn").mkdir(parents=True)
    (root / "latka_jazn/version.py").write_text('PACKAGE_VERSION="1.2.3"\n', encoding="utf-8")
    monkeypatch.setenv("JAZN_OPERATOR_STATE_ROOT", str(tmp_path / "operator"))
    store = RunStore(root)
    report = store.create(("chat-resume",), "python", {})
    report["results"][0].update(status="BLOCKED", reason="Model niedostępny")
    store.save(report)
    return app, store, report


def drain(app, panel):
    deadline = time.monotonic() + 10
    while panel.worker is not None and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.005)
    assert panel.worker is None


def test_real_qt_history_shows_missing_tests_and_block_reason(setup_history):
    app, store, report = setup_history
    panel = TestHistoryPanel(store.root)
    assert panel.table.rowCount() == 0 and panel.worker is None
    panel.refresh()
    drain(app, panel)
    assert panel.table.rowCount() == 22
    panel.resize(860, 580)
    panel.show()
    app.processEvents()
    assert panel.width() == 860 and panel.height() == 580
    panel.status.setCurrentText("BLOCKED")
    assert panel.table.rowCount() == 1
    reason = panel.table.item(0, 3)
    assert reason is not None and reason.text() == "Model niedostępny"
    assert "STATUS: BLOCKED" in panel.details.toPlainText()
    assert "RELEASE_NOT_ACCEPTED" in panel.summary.text()
    panel.status.setCurrentText("NOT_RUN")
    assert panel.table.rowCount() == 21
    panel.deleteLater()
    app.processEvents()


def test_corrupted_history_remains_visible_as_error(setup_history):
    app, store, report = setup_history
    (store.folder(report["run_id"]) / report["evidence_snapshot"] / "summary.json").write_text("{}", encoding="utf-8")
    panel = TestHistoryPanel(store.root)
    panel.refresh()
    drain(app, panel)
    assert panel.table.rowCount() == 0
    assert report["run_id"] in panel.errors.text()
    panel.deleteLater()
    app.processEvents()


def test_catalog_integrates_history_without_automatic_reads(setup_history):
    app, store, report = setup_history
    panel = TestCatalogPanel(store.root)
    assert isinstance(panel.history_panel, TestHistoryPanel)
    assert panel.history_panel.worker is None
    panel.resize(860, 580)
    panel.show()
    app.processEvents()
    assert panel.history_panel.table.rowCount() == 0
    panel.close()
    panel.deleteLater()
    app.processEvents()
