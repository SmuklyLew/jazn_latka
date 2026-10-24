"""Qt native Test Studio catalogue: read-only inspection (P2/P3 partial)."""
from __future__ import annotations

import os
import pytest

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication, QTableWidget
from tools.jazn_run_studio import test_catalog_view as view


@pytest.fixture
def panel(tmp_path, monkeypatch):
    if os.name != "nt" and not os.environ.get("DISPLAY"):
        monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])
    widget = view.TestCatalogPanel(tmp_path)
    yield widget
    widget.close()
    app.processEvents()


def test_native_catalog_is_read_only_and_loads_on_request(panel, monkeypatch):
    calls = []
    def fake_filtered(root, *, query, status):
        calls.append((root, query, status))
        return [
            ("tests/test_a.py::test_ok", {
                "purpose": "Weryfikuj integralność",
                "expected": "Wszystkie asercje przechodzą",
                "category": "unit",
                "status": "current",
            })
        ]
    monkeypatch.setattr(view, "filtered", fake_filtered)
    assert panel.table.rowCount() == 0
    panel.query.setText("integralność")
    panel.refresh()
    assert calls == [(panel.root, "integralność", "all")]
    assert panel.table.rowCount() == 1
    assert panel.table.editTriggers() == QTableWidget.EditTrigger.NoEditTriggers
    panel.table.setCurrentCell(0, 0)
    assert "Wszystkie asercje przechodzą" in panel.details.toPlainText()
    assert panel.details.isReadOnly()


def test_catalog_loading_failure_is_not_shown_as_zero_passed(panel, monkeypatch):
    def fail_filtered(*_args, **_kwargs):
        raise RuntimeError("private path not available")
    monkeypatch.setattr(view, "filtered", fail_filtered)
    panel.refresh()
    assert "Katalog niedostępny" in panel.summary.text()
    assert "private path" not in panel.summary.text()
    assert panel.table.rowCount() == 0


def test_catalog_limits_visible_rows_with_explicit_count(panel, monkeypatch):
    monkeypatch.setattr(view, "filtered", lambda *_args, **_kwargs: [
        (f"tests/t.py::test_{i}", {"category": "unit", "status": "current"})
        for i in range(310)
    ])
    panel.refresh()
    assert panel.table.rowCount() == 300
    assert "Znaleziono 310" in panel.summary.text()
    assert "pokazano 300" in panel.summary.text()
