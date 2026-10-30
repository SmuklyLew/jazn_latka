"""Isolated Qt contracts for the unified operator dock.

These synthetic tests do not claim live runtime, PTY, or model acceptance.
"""
from __future__ import annotations

import pytest

pytest.importorskip("PySide6")
from tests.test_jazn_run_studio_layout import window  # noqa: F401
from tools.jazn_run_studio.workspace_layout import SCHEMA, validate


def test_production_route_reuses_single_bottom_dock(window) -> None:
    window.unified_operator_mode = True
    window.set_logs_visible(True)
    assert window.workspace.dock.isVisible()
    assert window.workspace.tabs.currentIndex() == 1
    assert not window.tabs.isVisible()

    view = window.show_log("diagnostics:unified")
    assert view.isReadOnly()
    assert window.workspace.dock.isVisible()
    assert not window.tabs.isVisible()
    window.toggle_logs()
    assert not window.workspace.dock.isVisible()
    window.toggle_logs()
    assert window.workspace.dock.isVisible()
    assert not window.tabs.isVisible()


def test_shared_history_and_technical_panels_are_safe_read_only(window) -> None:
    workspace = window.workspace
    assert workspace.tabs.tabText(3) == "Historia"
    assert workspace.tabs.tabText(4) == "Techniczne"
    assert workspace.tabs.tabText(5) == "Terminal PTY"
    assert not workspace.interactive_terminal.pty.process
    assert workspace.consoles_splitter.count() == 3
    assert all(console.output.isReadOnly() for console in workspace.consoles)
    workspace.refresh_history()
    assert "historia TPA:" in workspace.history_summary.text()
    workspace.refresh_technical()
    assert workspace.technical.isReadOnly()
    assert "local_studio_read_only" in workspace.technical.toPlainText()
    assert "not_verified_by_this_panel" in workspace.technical.toPlainText()


def test_layout_v3_restores_valid_prior_schemas_but_rejects_bad_tab() -> None:
    assert validate({"schema": SCHEMA, "operator_tab": 4})["operator_tab"] == 4
    assert validate({"schema": SCHEMA, "operator_tab": 5})["operator_tab"] == 5
    assert validate({"schema": "jazn_heart_layout/v2", "dock_visible": True})["schema"] == SCHEMA
    assert validate({"schema": "jazn_heart_layout/v1"})["schema"] == SCHEMA
    for invalid in (-1, 6, 1.2, True, "2"):
        with pytest.raises(ValueError):
            validate({"schema": SCHEMA, "operator_tab": invalid})
