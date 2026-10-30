"""Qt integration for JSS theme selection; synthetic, not live runtime acceptance."""
from __future__ import annotations

from dataclasses import asdict

import pytest

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QScrollArea

from tests.test_jazn_run_studio_layout import window
from tools.jazn_run_studio.core import load_settings
from tools.jazn_run_studio.workbench_theme import WORKBENCH_PROFILES, workbench_colors


@pytest.mark.parametrize("theme", [p.key for p in WORKBENCH_PROFILES])
def test_toolbar_selection_persists_and_does_not_operate_services(window, theme: str) -> None:
    expected_count = len(window.core.jobs)
    index = window.style_selector.findData(theme)
    assert index >= 0
    window.style_selector.setCurrentIndex(index)
    assert window.core.settings.theme == theme
    assert window.theme.currentData() == theme
    saved, _ = load_settings(window.core.root)
    assert saved.theme == theme
    assert len(window.core.jobs) == expected_count
    assert "niezweryfikowany" in window.workbench_status.text()
    assert window.style_selector.accessibleName()
    assert window.current_section.text() == "Pulpit"
    assert window.palette().color(window.palette().ColorRole.Window).name().lower() == (
        workbench_colors(theme, window.core.settings.accent).background.lower()
    )


def test_unsaved_form_is_not_discarded_on_toolbar_selection(window) -> None:
    window.fields["mcp_port"].setText("8999")
    assert window.settings_draft() != window.settings_baseline
    saved = window.core.settings.theme
    index = window.style_selector.findData("operations-studio")
    window.style_selector.setCurrentIndex(index)
    assert window.core.settings.theme == saved
    assert window.style_selector.currentData() == saved
    assert window.fields["mcp_port"].text() == "8999"


def test_all_three_styles_preserve_navigation_and_panels(window) -> None:
    for profile in WORKBENCH_PROFILES:
        window.select_style(profile.key)
        window.navigate("Usługi i procesy")
        assert isinstance(window.pages.currentWidget(), QScrollArea)
        assert window.workbench.section_tabs.count() > 0
        assert window.services_table.rowCount() == 6
        assert window.style_selector.currentData() == profile.key
    actions = [action.text() for action in window.workbench.commands]
    assert all("Styl JSS: " + p.label in actions for p in WORKBENCH_PROFILES)
