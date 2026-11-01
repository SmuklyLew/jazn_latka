"""Advanced filters stay reachable while the TPA queue fits a small window."""
import pytest
pytest.importorskip("PySide6")
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from tests.test_jazn_run_studio_layout import window


def test_collapsed_filters_keep_search_and_keyboard_access(window):
    window.resize(860, 580)
    window.navigate("TPA")
    panel = window.local_acceptance_panel
    assert panel.search.isVisible()
    assert not panel.filter_details.isVisible()
    panel.filter_toggle.setFocus()
    QTest.keyClick(panel.filter_toggle, Qt.Key.Key_Space)
    assert panel.filter_details.isVisible()
    assert panel.category.isVisible() and panel.triage_filter.isVisible()
    panel.triage_filter.setCurrentIndex(panel.triage_filter.findData("DO_POWTORZENIA"))
    assert all(panel.table.isRowHidden(row) for row in range(panel.table.rowCount()))
    QTest.keyClick(panel.filter_toggle, Qt.Key.Key_Space)
    assert not panel.filter_details.isVisible()
