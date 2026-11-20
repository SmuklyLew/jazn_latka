"""Qt regression for read-only monitor tabs; no process or model is started."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication
from tools.jazn_monitor.window import MonitorWindow


@pytest.fixture(scope="module")
def app():
    existing = QApplication.instance()
    application = existing or QApplication([])
    yield application


def test_monitor_renders_process_jobs_and_finalization_independently(app):
    window = MonitorWindow(None, 8787, 11434, smoke=True)
    payload = {
        "observed_at_utc": "2026-11-20T15:00:00+00:00",
        "services": {
            "Daemon Jaźni": {"state": "ready", "detail": "PID 1357"},
            "Ollama": {"state": "unavailable", "detail": "API unreachable"},
        },
        "processes": {
            "state": "available",
            "items": [{"name": "Jaźń — Daemon", "pid": 1357, "parent_pid": 100,
                       "cpu_seconds": 6.25, "ram_mb": 75.5,
                       "uptime_seconds": 92, "evidence": "verified_instance"}],
        },
        "jobs": {
            "state": "available", "counts": {
                "submitted_total": 2, "completed_total": 1,
                "failed_non_timeout_total": 1,
                "execution_timeout_total": 0, "pending": 0,
            },
            "items": [{"request_id": "aaaa-1111", "state": "failed",
                       "duration_seconds": 17, "error_code": "runtime_turn_not_accepted",
                       "reason_code": "classified_non_dynamic_response"}],
        },
        "finalization": {"state": "rejected", "request_id": "aaaa-1111",
                         "error_code": "runtime_turn_not_accepted",
                         "reason_code": "classified_non_dynamic_response"},
    }
    window.apply_snapshot(payload)
    assert window.table.item(0, 1).text() == "GOTOWY"
    assert window.table.item(2, 1).text() == "NIEDOSTĘPNY"
    assert window.tabs.count() == 4
    assert window.process_table.rowCount() == 1
    assert window.process_table.item(0, 0).text() == "Jaźń — Daemon"
    assert window.process_table.item(0, 3).text() == "6.25"
    assert window.job_table.rowCount() == 1
    assert window.job_table.item(0, 3).text() == "runtime_turn_not_accepted"
    assert "classified_non_dynamic_response" in window.final_label.text()
    assert "ukończone 1" in window.job_counts.text()
    assert "PRIVATE MESSAGE" not in window.final_label.text()
    window.close()
