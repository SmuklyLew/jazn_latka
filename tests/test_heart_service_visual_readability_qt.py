"""Selection must keep embedded service labels readable in every profile."""
from dataclasses import replace

import pytest

pytest.importorskip("PySide6")
from PySide6.QtGui import QPalette
from PySide6.QtTest import QTest

from tests.test_jazn_run_studio_layout import window
from tools.jazn_run_studio.workbench_theme import contrast_ratio


@pytest.mark.parametrize("theme", ["violet-night", "system", "light", "dark", "purple", "custom"])
def test_selected_service_labels_remain_readable_and_rows_are_compact(window, theme):
    window.core.settings = replace(window.core.settings, theme=theme)
    window.apply_theme()
    window.navigate("Usługi i procesy")
    window.services_table.selectRow(0)
    QTest.qWait(20)
    label = window.statuses["runtime"]
    foreground = label.palette().color(QPalette.ColorRole.WindowText).name()
    background = label.palette().color(QPalette.ColorRole.Window).name()
    assert contrast_ratio(foreground, background) >= 4.5
    assert window.services_table.verticalHeader().defaultSectionSize() == 48
    assert "sprawdzono" in label.text()
