"""The live opt-in stays keyboard accessible without widening the TPA queue."""
import sys

import pytest
pytest.importorskip("PySide6")
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from tools.jazn_run_studio.tpa_view import TPAPanel
from tests.test_tpa_2_current_state import store


def test_live_optin_is_reachable_inside_collapsed_environment_settings(store):
    app = QApplication.instance() or QApplication([])
    panel = TPAPanel(store.root, python=sys.executable)
    try:
        panel.show()
        app.processEvents()
        assert panel.live_plan.parent() is panel.setup_details
        assert not panel.live_plan.isChecked()
        assert not panel.setup_details.isVisible()
        panel.setup_toggle.setFocus()
        QTest.keyClick(panel.setup_toggle, Qt.Key.Key_Space)
        app.processEvents()
        assert panel.live_plan.isVisible()
        panel.live_plan.setFocus()
        QTest.keyClick(panel.live_plan, Qt.Key.Key_Space)
        assert panel.live_plan.isChecked()
        QTest.keyClick(panel.setup_toggle, Qt.Key.Key_Space)
        assert not panel.setup_details.isVisible()
        assert panel.live_plan.isChecked()  # collapsing does not revoke consent
    finally:
        panel.close()
        app.processEvents()
