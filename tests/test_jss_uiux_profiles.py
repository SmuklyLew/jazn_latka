"""JSS visual contracts: deterministic profiles and safe settings (no live runtime)."""
from __future__ import annotations

from dataclasses import asdict

import pytest

from tools.jazn_run_studio.core import Settings, StudioError
from tools.jazn_run_studio.workbench_theme import (
    DEFAULT_WORKBENCH_THEME, LEGACY_THEMES, THEME_CHOICES, WORKBENCH_PROFILES,
    contrast_ratio, theme_label, workbench_colors, workbench_metrics, workbench_stylesheet,
)


def test_default_and_migration_do_not_require_a_running_daemon() -> None:
    assert Settings().theme == DEFAULT_WORKBENCH_THEME == "technical-workbench"
    assert Settings.validate(asdict(Settings())).theme == DEFAULT_WORKBENCH_THEME
    for old in LEGACY_THEMES:
        assert Settings.validate({"theme": old}).theme == old
    for profile in WORKBENCH_PROFILES:
        assert Settings.validate({"theme": profile.key}).theme == profile.key
    with pytest.raises(StudioError):
        Settings.validate({"theme": "untrusted-qss"})


def test_profiles_are_distinct_and_reusable_for_future_token_composition() -> None:
    assert [p.key for p in WORKBENCH_PROFILES] == [
        "technical-workbench", "operations-studio", "fluent-studio"
    ]
    assert len({p.key for p in WORKBENCH_PROFILES}) == len(WORKBENCH_PROFILES)
    assert len({p.metrics for p in WORKBENCH_PROFILES}) == len(WORKBENCH_PROFILES)
    assert WORKBENCH_PROFILES[0].metrics.gap < WORKBENCH_PROFILES[-1].metrics.gap
    assert all(theme_label(p.key) == p.label for p in WORKBENCH_PROFILES)
    assert len({key for _, key in THEME_CHOICES}) == len(THEME_CHOICES)
    assert workbench_metrics("dark").control_height > 0


@pytest.mark.parametrize("theme", [p.key for p in WORKBENCH_PROFILES])
def test_color_and_accessibility_of_new_styles(theme: str) -> None:
    colors = workbench_colors(theme, "#5BA5F5")
    for surface in (colors.background, colors.sidebar, colors.editor):
        assert contrast_ratio(colors.text, surface) >= 4.5
        assert contrast_ratio(colors.muted, surface) >= 4.5
    for surface in (colors.background, colors.sidebar, colors.surface, colors.hover):
        assert contrast_ratio(colors.border, surface) >= 3
    assert contrast_ratio(colors.selected_text, colors.accent) >= 4.5
    assert contrast_ratio(colors.focus, colors.background) >= 3
    for status in (colors.success, colors.warning, colors.error):
        assert contrast_ratio(status, colors.background) >= 4.5
    qss = workbench_stylesheet(theme, "#5BA5F5")
    assert "QDockWidget::title" in qss
    assert "#workbenchNavigation" in qss
    assert "background-image" not in qss
    assert "http:" not in qss and "https:" not in qss


def test_invalid_accent_fails_closed() -> None:
    for invalid in ("red", "#AAA", "#112233;}", "not_a_color"):
        with pytest.raises(ValueError):
            workbench_stylesheet("technical-workbench", invalid)
