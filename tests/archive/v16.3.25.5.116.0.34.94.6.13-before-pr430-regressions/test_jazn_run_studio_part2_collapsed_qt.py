"""Manual log-panel collapse is a user preference, not a one-event timeout."""
from __future__ import annotations

import pytest

pytest.importorskip("PySide6")
from tests.test_jazn_run_studio_layout import window


def test_new_error_tab_does_not_reopen_manually_collapsed_logs(window) -> None:
    window.log_view("service:ollama")
    assert window.tabs.isVisible()
    window.toggle_logs()
    assert window.logs_user_hidden and not window.tabs.isVisible()

    window.core.emit("probe:gateway", "state", {
        "state": "failed", "pid": None, "error": "service_not_ready",
    })
    window.poll()

    assert "Błędy" in window.logs
    assert "Zdarzenia" in window.logs
    assert window.logs_user_hidden
    assert not window.tabs.isVisible()
    window.toggle_logs()
    assert window.tabs.isVisible()
    assert "service_not_ready" in window.logs["Błędy"].toPlainText()
