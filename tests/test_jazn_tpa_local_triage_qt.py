"""Smoke test for explicit read-only local TPA triage UI."""
from __future__ import annotations

import sys
import pytest
pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication

from tools.jazn_run_studio.tpa_view import TPAPanel


def test_local_triage_filter_and_acceptance_tab(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    root = tmp_path / "system"
    root.mkdir()
    monkeypatch.setenv("JAZN_OPERATOR_STATE_ROOT", str(tmp_path / "operator"))
    panel = TPAPanel(root, python=sys.executable)
    try:
        assert len(panel.rows) == 22
        assert panel.triage_filter.findData("NOWE") >= 0
        assert panel.triage_filter.findData("DO_POWTORZENIA") >= 0
        assert panel.triage_filter.findData("NIEAKTUALNE") >= 0
        assert "Odbiory lokalne" in [panel.tabs.tabText(i) for i in range(panel.tabs.count())]
        assert "PTY Windows" in panel.local_gates_view.toPlainText()
        assert panel.report is None
        panel.triage_filter.setCurrentIndex(panel.triage_filter.findData("DO_POWTORZENIA"))
        assert all(panel.table.isRowHidden(i) for i in range(panel.table.rowCount()))
        panel.triage_filter.setCurrentIndex(panel.triage_filter.findData("NOWE"))
        assert not any(panel.table.isRowHidden(i) for i in range(panel.table.rowCount()))
    finally:
        panel.close()
        app.processEvents()
