"""Closing a section tab never destroys its view or runtime ownership."""
from __future__ import annotations

import pytest

pytest.importorskip("PySide6")
from tests.test_jazn_run_studio_layout import window  # noqa: F401


def test_workspace_tabs_close_and_reopen_same_section(window) -> None:
    tabs = window.workbench.section_tabs
    assert tabs.tabsClosable()
    assert tabs.isMovable()

    window.navigate("Pulpit")
    window.navigate("Ustawienia")
    page = window.pages.currentWidget()
    assert window.current_section.text() == "Ustawienia"
    index = next(i for i in range(tabs.count()) if tabs.tabText(i) == "Ustawienia")
    count_before = tabs.count()

    window.workbench.close_section_tab(index)
    assert tabs.count() == count_before - 1
    assert all(tabs.tabText(i) != "Ustawienia" for i in range(tabs.count()))

    window.navigate("Ustawienia")
    assert any(tabs.tabText(i) == "Ustawienia" for i in range(tabs.count()))
    assert window.pages.currentWidget() is page


def test_closing_last_tab_preserves_view_and_does_not_start_runtime(window) -> None:
    tabs = window.workbench.section_tabs
    while tabs.count() > 0:
        window.workbench.close_section_tab(tabs.count() - 1)
    assert tabs.count() == 0
    before = len(window.core.jobs)
    window.navigate(window.current_section.text())
    assert tabs.count() == 1
    assert len(window.core.jobs) == before
