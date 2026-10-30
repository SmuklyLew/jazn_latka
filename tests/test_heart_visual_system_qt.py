"""Visual behavior across native pages; never certifies twelve-Studio parity."""
from dataclasses import replace

import pytest

pytest.importorskip("PySide6")
from PySide6.QtCore import Qt
from PySide6.QtGui import QPalette
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QDialog, QLineEdit, QScrollArea, QTableWidget

from tests.test_jazn_run_studio_layout import window
from tools.jazn_run_studio.workbench_theme import contrast_ratio, workbench_colors
from tools.jazn_run_studio.workspace_layout import SCHEMA, validate


@pytest.mark.parametrize("theme", ["violet-night", "system", "light", "dark", "purple", "custom"])
@pytest.mark.parametrize("accent", ["#000000", "#ffffff", "#345678"])
def test_all_profiles_have_readable_text_selection_status_and_focus(theme, accent):
    for system_dark in (False, True):
        c = workbench_colors(theme, accent, system_dark=system_dark)
        assert contrast_ratio(c.text, c.background) >= 4.5
        assert contrast_ratio(c.muted, c.background) >= 4.5
        assert contrast_ratio(c.selected_text, c.accent) >= 4.5
        assert contrast_ratio(c.focus, c.background) >= 3
        for semantic in (c.error, c.warning, c.success):
            assert contrast_ratio(semantic, c.background) >= 4.5


@pytest.mark.parametrize("theme", ["violet-night", "system", "light", "dark", "purple", "custom"])
def test_theme_covers_all_pages_tables_and_new_parented_dialogs(window, theme):
    window.core.settings = replace(window.core.settings, theme=theme)
    window.apply_theme()
    for row in range(window.nav.count()):
        window.nav.setCurrentRow(row)
        page = window.pages.currentWidget()
        assert isinstance(page, QScrollArea)
        assert page.palette().color(QPalette.ColorRole.WindowText) == window.palette().color(QPalette.ColorRole.WindowText)
    dialog = QDialog(window)
    field = QLineEdit(dialog)
    dialog.show()
    QTest.qWait(10)
    assert field.palette().color(QPalette.ColorRole.Text) == window.palette().color(QPalette.ColorRole.Text)
    assert all(t.alternatingRowColors() for t in window.findChildren(QTableWidget))
    dialog.close()


def test_menus_palette_tabs_and_keyboard_use_existing_navigation(window):
    assert [a.text() for a in window.menuBar().actions()] == ["Plik", "Edycja", "Widok", "Terminal", "Usługi", "Jaźń", "Studia", "TPA", "Narzędzia", "Pomoc"]
    window.workbench.open_palette()
    palette = window.workbench.palette_dialog
    assert palette is not None
    palette.query.setText("Połączenie z ChatGPT")
    QTest.keyClick(palette.query, Qt.Key.Key_Return)
    assert window.current_section.text() == "Połączenie z ChatGPT"
    window.navigate("TPA")
    tabs = window.workbench.section_tabs
    target = next(i for i in range(tabs.count()) if tabs.tabText(i) == "Połączenie z ChatGPT")
    tabs.setCurrentIndex(target)
    assert window.current_section.text() == "Połączenie z ChatGPT"
    window.reset_layout()
    assert window.theme.currentText() == window.core.settings.theme


def test_layout_migrates_bounded_splitters_and_rejects_untrusted_fields():
    assert validate({"schema": "jazn_heart_layout/v1"})["schema"] == SCHEMA
    for value in ([1], [True, 100], [-1, 200], [1, 999999]):
        with pytest.raises(ValueError):
            validate({"schema": SCHEMA, "shell_sizes": value})
    with pytest.raises(ValueError):
        validate({"schema": SCHEMA, "open_sections": ["bad\nsection"]})


def test_minimum_window_retains_operational_pages_and_keyboard_focus(window):
    window.resize(860, 580)
    for title in ("Usługi i procesy", "Konfiguracja Qt", "Wersje Qt", "TPA", "Katalog testów", "Dowody MEMORY"):
        window.navigate(title)
        QTest.qWait(15)
        page = window.pages.currentWidget()
        assert isinstance(page, QScrollArea)
        assert page.horizontalScrollBar().maximum() == 0, title
    window.section_search.setFocus()
    QTest.keyClicks(window.section_search, "Developer")
    QTest.keyClick(window.section_search, Qt.Key.Key_Return)
    assert window.current_section.text() == "Developer"


def test_reflow_preserves_dynamic_labels_and_sidebar_preference(window):
    window.show_log("synthetic")
    window.visual_system.reflow()
    assert "Ukryj" in window.log_toggle.text()
    window.toggle_logs()
    window.visual_system.reflow()
    assert "Pokaż" in window.log_toggle.text()
    window.resize(860, 580)
    QTest.qWait(20)
    assert window.sidebar.isHidden()
    window.resize(1240, 840)
    QTest.qWait(20)
    assert not window.sidebar.isHidden()
