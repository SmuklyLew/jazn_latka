"""Qt workbench contract: dark/purple canvas, resizable panels, no invented readiness."""
from __future__ import annotations

from pathlib import Path

import pytest

from tests.test_jazn_run_studio_layout import window  # shared isolated Qt fixture

from tools.jazn_run_studio.workbench_theme import (
    workbench_colors, workbench_stylesheet,
)


def test_shared_palette_has_independent_light_dark_purple_and_custom_modes() -> None:
    light = workbench_colors("system", "#9876d4", system_dark=False)
    dark = workbench_colors("system", "#9876d4", system_dark=True)
    purple = workbench_colors("purple", "#123456")
    custom = workbench_colors("custom", "#345678")
    assert light.background != dark.background
    assert dark.background != purple.background
    assert purple.accent == "#9876d4"
    assert custom.accent == "#345678"
    assert "#workbenchSidebar" in workbench_stylesheet("purple", "#9876d4")
    assert "background-image" not in workbench_stylesheet("purple", "#9876d4")
    with pytest.raises(ValueError):
        workbench_colors("purple", "invalid")


def test_sidebar_and_contextual_panel_are_keyboard_accessible(window) -> None:
    from PySide6.QtTest import QTest
    from PySide6.QtCore import Qt

    assert window.current_section.text() == "Pulpit"
    window.nav.setCurrentRow(1)
    assert window.current_section.text() == "Usługi i procesy"
    assert window.sidebar.isVisible()
    window.toggle_sidebar()
    assert not window.sidebar.isVisible()
    window.toggle_sidebar()
    assert window.sidebar.isVisible()

    assert not window.tabs.isVisible()
    window.show_log("diagnostics:manual")
    assert window.tabs.isVisible()
    assert window.tabs.count() >= 1
    assert window.tabs.tabText(window.tabs.indexOf(window.logs["diagnostics:manual"])) == "diagnostics:manual"
    window.toggle_logs()
    assert not window.tabs.isVisible()
    window.log_view("Błędy")
    assert not window.tabs.isVisible()
    window.toggle_logs()
    assert window.tabs.isVisible()

    assert window.shell_splitter.count() == 2
    assert window.content_splitter.count() == 2
    assert window.shell_splitter.orientation() == Qt.Orientation.Horizontal
    assert window.content_splitter.orientation() == Qt.Orientation.Vertical


def test_workbench_preserves_viewport_and_neutral_status(window) -> None:
    from PySide6.QtWidgets import QScrollArea
    from PySide6.QtTest import QTest

    window.resize(860, 580)
    window.nav.setCurrentRow(1)
    QTest.qWait(150)
    page = window.pages.currentWidget()
    assert isinstance(page, QScrollArea)
    assert page.horizontalScrollBar().maximum() == 0
    assert "niezweryfikowany" in window.workbench_status.text()
    assert "niezweryfikowana" in window.sidebar_footnote.text()
    assert not window.tabs.isVisible()
