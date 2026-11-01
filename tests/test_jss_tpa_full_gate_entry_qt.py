"""TPA full acceptance is visibly reachable; regression PASS remains distinct."""
from __future__ import annotations
import pytest
pytest.importorskip("PySide6")
from PySide6.QtWidgets import QScrollArea
from tests.test_jazn_run_studio_layout import window


def test_full_acceptance_button_opens_scrollable_evidence_wizard(window) -> None:
    window.navigate("TPA")
    panel = window.local_acceptance_panel
    assert panel.full_acceptance_button.isEnabled()
    assert "Pełny odbiór" in panel.full_acceptance_button.text()
    panel.full_acceptance_button.click()
    assert isinstance(panel.guide_page, QScrollArea)
    assert panel.guide_page.widgetResizable()
    assert panel.tabs.currentWidget() is panel.guide_page
    assert panel._wizard_active
    assert panel.cell(0, 3).text() == "NOT_RUN"
    assert "Kopia testowa SYSTEM" in panel.acceptance_environment.text()
    assert "Trwałe dowody" in panel.acceptance_environment.text()


def test_command_palette_opens_full_acceptance_without_generating_pass(window) -> None:
    window.workbench.open_palette()
    palette = window.workbench.palette_dialog
    palette.query.setText("Rozpocznij pełny odbiór")
    palette.execute()
    assert window.current_section.text() == "TPA"
    assert window.local_acceptance_panel.tabs.currentWidget() is window.local_acceptance_panel.guide_page
    assert window.local_acceptance_panel.cell(0, 3).text() == "NOT_RUN"
