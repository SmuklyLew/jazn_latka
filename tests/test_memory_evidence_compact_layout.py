"""Long observation timestamps and expanded pins must fit a small viewport."""
import pytest

pytest.importorskip("PySide6")
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QScrollArea

from tests.test_jazn_run_studio_memory_view import window
from tools.jazn_run_studio.window import Window


@pytest.mark.parametrize("expanded", [False, True])
def test_completed_memory_observation_fits_minimum_width(window: Window, expanded: bool) -> None:
    window.resize(860, 580)
    window.nav.setCurrentRow(5)
    panel = window.memory_panel
    panel.pin_toggle.setChecked(expanded)
    panel.pending["readiness"] = 1.0
    panel.receive("memory:p1:readiness", {"started": 1.0,
        "report": {"ok": True, "result": {"runtime_ready": False}}})
    panel.tabs.setCurrentIndex(2)
    QTest.qWait(150)
    page = window.pages.currentWidget()
    assert isinstance(page, QScrollArea)
    assert page.horizontalScrollBar().maximum() == 0
