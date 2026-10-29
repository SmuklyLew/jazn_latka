"""Qt Heart console gives lifecycle actions only to canonically owned services."""
from __future__ import annotations

import pytest
pytest.importorskip("PySide6")
from tests.test_jazn_run_studio_layout import window


def test_heart_console_modules_and_readonly_actions(window):
    assert list(window.service_rows) == [
        "runtime", "ollama", "gateway", "cloudflare", "supervisor", "memory"
    ]
    for key in ("cloudflare", "supervisor", "memory"):
        window.services_table.selectRow(window.service_rows[key])
        window.refresh_service_controls()
        assert not window.service_start_button.isEnabled()
        assert not window.service_stop_button.isEnabled()
        assert not window.service_restart_button.isEnabled()
    window.services_table.selectRow(window.service_rows["gateway"])
    window.refresh_service_controls()
    assert window.service_start_button.isEnabled()
    assert not window.service_stop_button.isEnabled()


def test_unverified_supervisor_cannot_be_green(window):
    row = window.service_rows["supervisor"]
    window.core.emit("supervisor", "supervisor_evidence", {"ready": False, "pid": 1234})
    window.poll()
    assert window.services_table.item(row, 4).text() == "niezweryfikowana"
    window.core.emit("supervisor", "supervisor_evidence", {"ready": True, "pid": 1234})
    window.poll()
    assert window.services_table.item(row, 4).text() == "potwierdzona"
    assert window.services_table.item(row, 2).text() == "1234"
    window.core.emit("supervisor", "state", {"state": "failed", "error": "invalid_supervisor_status_json"})
    window.poll()
    assert window.services_table.item(row, 4).text() == "niezweryfikowana"
    assert "BŁĄD" in window.statuses["supervisor"].text()


def test_memory_is_technical_status_without_lifecycle(window):
    window.core.emit("status", "status_summary", {"memory": "dostępna technicznie; recall niepotwierdzony"})
    window.poll()
    row = window.service_rows["memory"]
    assert window.services_table.item(row, 4).text() == "status techniczny"
    assert "recall niepotwierdzony" in window.statuses["memory"].text()
    window.services_table.selectRow(row)
    with pytest.raises(ValueError, match="tylko diagnostykę"):
        window.selected_service_action("start")
