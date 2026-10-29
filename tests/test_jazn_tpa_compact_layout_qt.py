"""A small real workbench leaves room for the queue, with keyboard setup access."""
import pytest
pytest.importorskip("PySide6")
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from tests.test_jazn_run_studio_layout import window


def test_minimum_window_exposes_queue_and_expandable_setup_from_keyboard(window):
    window.resize(860, 580)
    window.navigate("TPA")
    QTest.qWait(30)
    panel = window.local_acceptance_panel
    assert not panel.setup_details.isVisible()
    page = window.pages.currentWidget()
    page.verticalScrollBar().setValue(0)
    QTest.qWait(30)
    assert panel.table.mapTo(page.viewport(), panel.table.rect().topLeft()).y() < page.viewport().height() - 70
    panel.setup_toggle.setFocus()
    QTest.keyClick(panel.setup_toggle, Qt.Key.Key_Space)
    assert panel.setup_details.isVisible()
    QTest.keyClick(panel.setup_toggle, Qt.Key.Key_Space)
    assert not panel.setup_details.isVisible()
