"""Dashboard shortcuts and operator dock must stay unambiguous in JSS."""
from __future__ import annotations

import pytest

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QPushButton
from tests.test_jazn_run_studio_layout import window  # noqa: F401


def test_dashboard_omits_redundant_setup_and_chat_shortcuts(window) -> None:
    window.navigate("Pulpit")
    page = window.pages.currentWidget()
    texts = {button.text() for button in page.findChildren(QPushButton)}
    assert "Kreator konfiguracji…" not in texts
    assert "3. Przejdź do rozmowy" not in texts
    assert "Stany usług — monitor" in texts


def test_operator_tools_status_action_toggles_existing_dock(window) -> None:
    assert window.operator_status.text() == "Narzędzia Operatora"
    assert not window.workspace.dock.isVisible()
    window.operator_status.click()
    assert window.workspace.dock.isVisible()
    window.operator_status.click()
    assert not window.workspace.dock.isVisible()
