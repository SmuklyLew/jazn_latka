"""Regression for Linux native Qt crash while switching JSS visual profiles.

Keep the real JSS widget hierarchy and keep the test in Qt offscreen mode.
No runtime, service, MCP or MEMORY operation is necessary.
"""
from __future__ import annotations

import pytest

pytest.importorskip("PySide6")
from PySide6.QtTest import QTest
from tests.test_jazn_run_studio_layout import window
from tools.jazn_run_studio.workbench_theme import WORKBENCH_PROFILES


def test_repeated_theme_switch_reflow_is_safe_for_all_profiles(window) -> None:
    visual = window.visual_system
    for _ in range(3):
        for profile in WORKBENCH_PROFILES:
            window.select_style(profile.key)
            window.navigate("Usługi i procesy")
            visual.reflow()
            QTest.qWait(25)
            assert window.core.settings.theme == profile.key
            assert window.services_table.rowCount() == 6
            assert not visual._closed
    window.close()
    assert visual._closed
    assert not visual._reflow_timer.isActive()
