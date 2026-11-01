"""Regression coverage for the part-2 operator desktop controls.

All evidence in these tests is synthetic; they do not claim live daemon readiness.
"""
from __future__ import annotations

import importlib

import pytest

pytest.importorskip("PySide6")
from PySide6.QtGui import QColor
from tests.test_jazn_run_studio_layout import window


def test_dashboard_mirrors_observed_process_without_claiming_readiness(window) -> None:
    window.core.emit("service:ollama", "state", {
        "state": "running", "pid": 871, "error": None,
    })
    window.poll()
    assert "PID 871" in window.statuses["ollama"].text()
    assert "niezweryfikowana" in window.dashboard_statuses["ollama"].text()
    assert "PID 871" in window.dashboard_statuses["ollama"].text()

    window.core.emit("probe:ollama", "state", {
        "state": "failed", "pid": None, "error": "selected_model_missing",
    })
    window.poll()
    assert "BŁĄD testu" in window.statuses["ollama"].text()
    assert "selected_model_missing" in window.dashboard_statuses["ollama"].text()


def test_runtime_ready_requires_explicit_evidence(window) -> None:
    window.core.emit("status", "evidence", {
        "active_state": "unverified",
        "endpoint_reachable": True,
        "process_identity_confirmed": False,
        "conversation_ready": False,
    })
    window.poll()
    label = window.dashboard_statuses["runtime"].text()
    assert "tożsamość procesu: niepotwierdzone" in label
    assert "gotowość rozmowy: niepotwierdzone" in label


def test_lower_logs_panel_can_be_hidden_and_restored(window) -> None:
    window.show_log("status")
    assert window.tabs.isVisible()
    window.toggle_logs()
    assert not window.tabs.isVisible()
    assert window.log_toggle.text() == "Pokaż logi"
    window.toggle_logs()
    assert window.tabs.isVisible()
    assert window.log_toggle.text() == "Ukryj logi"


def test_color_palette_accepts_valid_selection_without_premature_save(window, monkeypatch) -> None:
    gui = importlib.import_module("tools.jazn_run_studio.view_settings")

    class Accepted:
        @staticmethod
        def getColor(*_args, **_kwargs):
            return QColor("#345678")

    monkeypatch.setattr(gui, "QColorDialog", Accepted)
    previous_digest = window.digest
    window.choose_custom_color()
    assert window.fields["accent"].text() == "#345678"
    assert window.theme.currentText() == "custom"
    assert window.digest == previous_digest
    assert window.core.settings.theme == "dark"


def test_color_palette_cancel_keeps_draft(window, monkeypatch) -> None:
    gui = importlib.import_module("tools.jazn_run_studio.view_settings")

    class Cancelled:
        @staticmethod
        def getColor(*_args, **_kwargs):
            return QColor()

    monkeypatch.setattr(gui, "QColorDialog", Cancelled)
    before = (window.fields["accent"].text(), window.theme.currentText())
    window.choose_custom_color()
    assert (window.fields["accent"].text(), window.theme.currentText()) == before
