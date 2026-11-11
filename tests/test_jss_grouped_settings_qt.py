"""Grouped Settings filters must preserve drafts and never operate services."""
from __future__ import annotations

import pytest

pytest.importorskip("PySide6")
from tests.test_jazn_run_studio_layout import window  # noqa: F401


def test_settings_groups_and_category_filter_preserve_unsaved_fields(window) -> None:
    window.navigate("Ustawienia")
    expected = {"Środowisko", "Runtime", "Modele", "MCP", "Cloudflare",
                "Bezpieczeństwo", "Wygląd"}
    assert set(window.settings_group_headers) == expected
    before_jobs = len(window.core.jobs)
    window.fields["mcp_port"].setText("18888")

    window.settings_category.setCurrentText("MCP")
    window.filter_settings()
    assert window.settings_group_headers["MCP"].isVisible()
    assert all(
        not label.isVisible()
        for category, label in window.settings_group_headers.items()
        if category != "MCP"
    )
    assert window.fields["mcp_port"].isVisible()
    assert not window.fields["python"].isVisible()
    assert window.fields["mcp_port"].text() == "18888"

    window.settings_category.setCurrentText("Wszystkie")
    window.settings_search.clear()
    window.filter_settings()
    assert all(label.isVisible() for label in window.settings_group_headers.values())
    assert window.fields["mcp_port"].text() == "18888"
    assert len(window.core.jobs) == before_jobs
