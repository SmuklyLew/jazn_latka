"""Focused, isolated two-theme and operator panel behavior contracts.

These tests do not assert real Windows ConPTY, daemon readiness, or TPA full_gate.
"""
from __future__ import annotations

import pytest

pytest.importorskip("PySide6")
from tests.test_jazn_run_studio_layout import window  # noqa: F401
from tools.jazn_run_studio.core import Settings, preferred_theme
from tools.jazn_run_studio.workbench_theme import workbench_colors, contrast_ratio
from tools.jazn_run_studio.workspace_layout import SCHEMA, validate


def test_two_operator_defaults_and_safe_legacy_presentation() -> None:
    assert Settings().theme == "dark"
    assert preferred_theme("violet-night") == "dark"
    assert preferred_theme("purple") == "dark"
    assert preferred_theme("custom") == "dark"
    assert preferred_theme("system") == "dark"
    assert preferred_theme("light") == "light"
    assert preferred_theme("dark") == "dark"


def test_light_and_dark_visual_contracts_keep_text_readable() -> None:
    light = workbench_colors("light", "#A783DB")
    dark = workbench_colors("dark", "#A783DB")
    assert light.background != dark.background
    assert light.sidebar != dark.sidebar
    assert contrast_ratio(light.background, light.text) >= 7
    assert contrast_ratio(dark.background, dark.text) >= 7
    assert contrast_ratio(light.accent, light.selected_text) >= 4.5
    assert contrast_ratio(dark.accent, dark.selected_text) >= 4.5


def test_window_only_offers_two_named_appearances(window) -> None:
    assert window.theme.count() == 2
    assert [(window.theme.itemText(i), window.theme.itemData(i)) for i in range(2)] == [
        ("Ciemny", "dark"), ("Jasny", "light")
    ]
    window.theme.setCurrentIndex(1)
    assert window.settings_draft()["theme"] == "light"
    window.theme.setCurrentIndex(0)
    assert window.settings_draft()["theme"] == "dark"


def test_operator_tab_and_height_are_bounded_and_backward_compatible() -> None:
    current = validate({"schema": SCHEMA, "operator_tab": 4, "dock_height": 400})
    assert current["operator_tab"] == 4
    assert current["dock_height"] == 400
    assert validate({"schema": "jazn_heart_layout/v2"})["schema"] == SCHEMA
    for bad in (179, 3001, -4, 200.4, True, "500"):
        with pytest.raises(ValueError):
            validate({"schema": SCHEMA, "dock_height": bad})


def test_selected_service_cell_widget_keeps_contrast_in_both_modes(window) -> None:
    from dataclasses import replace
    for theme in ("dark", "light"):
        window.core.settings = replace(window.core.settings, theme=theme)
        window.apply_theme()
        window.services_table.selectRow(1)
        window.refresh_service_controls()
        colors = workbench_colors(theme, window.core.settings.accent)
        selected_css = window.statuses["ollama"].styleSheet()
        plain_css = window.statuses["runtime"].styleSheet()
        assert f"background: {colors.accent}" in selected_css
        assert f"color: {colors.selected_text}" in selected_css
        assert f"color: {colors.text}" in plain_css
