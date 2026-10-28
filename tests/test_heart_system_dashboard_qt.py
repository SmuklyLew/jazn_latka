"""Actual Qt dashboard clears old positive status after a failed observation."""
from __future__ import annotations
import pytest
pytest.importorskip("PySide6")
from PySide6.QtCore import Qt
from tests.test_jazn_run_studio_layout import window
from tools.jazn_run_studio.core import daemon_evidence
from tools.jazn_run_studio.status_summary import status_summary
from tests.test_heart_system_dashboard import observation


def test_dashboard_updates_canonical_summary_and_invalidates_old_green(window) -> None:
    data = observation()
    window.core.emit("status", "status_summary", status_summary(data))
    window.poll()
    assert window.dashboard_summary["integrity"].text() == "zweryfikowane"
    assert "wyłączona" in window.dashboard_summary["memory"].text()
    assert window.dashboard_summary["version"].text() == "16.3-test"
    window.core.emit("status", "evidence", daemon_evidence({}))
    window.core.emit("status", "status_summary", status_summary({}))
    window.core.emit("status", "state", {"state": "failed", "error": "invalid_status_json"})
    window.poll()
    assert window.dashboard_summary["integrity"].text() == "niezweryfikowane"
    assert "Gotowość niezweryfikowana" in window.evidence.text()
    assert "BŁĄD" in window.dashboard_last_operation.text()
    assert window.workspace.failures["status"]["error"] == "invalid_status_json"


def test_dashboard_uses_plain_text_for_selected_system_values(window) -> None:
    data = observation(); data["runtime_version"] = "<b>external system</b>"
    window.core.emit("status", "status_summary", status_summary(data))
    window.poll()
    label = window.dashboard_summary["version"]
    assert label.textFormat() == Qt.TextFormat.PlainText
    assert label.text() == "<b>external system</b>"
