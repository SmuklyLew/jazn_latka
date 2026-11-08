"""JSS monitoring surfaces must not expose lifecycle controls.

The standalone observer is polling-only; explicit process mutations remain
under the services operator view. No daemon, MCP or Ollama is launched here.
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QPushButton, QWidget

from tools.jazn_run_studio.service_status_dialog import ServiceStatusDialog
from tests.test_jazn_run_studio_layout import window  # noqa: F401


def test_service_observer_buttons_are_only_refresh_and_close() -> None:
    app = QApplication.instance() or QApplication([])
    assert app is not None
    host = QWidget()
    seen = []
    panel = ServiceStatusDialog(host, lambda: seen.append("read-only-poll"))
    labels = {button.text() for button in panel.findChildren(QPushButton)}
    assert labels == {"Odśwież stany", "Zamknij"}
    assert len(panel.indicators) == 7
    panel.request_refresh()
    assert seen == ["read-only-poll"]
    panel.close()
    host.close()


def test_service_table_per_row_buttons_are_read_only(window) -> None:
    for service, row in window.service_rows.items():
        button = window.services_table.cellWidget(row, 5)
        assert isinstance(button, QPushButton), service
        assert button.text() == "Odczytaj"
        assert button.menu() is None
    # Lifecycle remains available only after explicit operator selection
    # in the separate Services and processes page.
    assert window.service_start_button.text() == "Start"
    assert window.service_stop_button.text() == "Stop"
    assert window.service_restart_button.text() == "Restart"


def test_dashboard_has_no_mutating_start_shortcuts(window) -> None:
    from tools.jazn_run_studio.view_dashboard import DashboardViewMixin
    import inspect

    source = inspect.getsource(DashboardViewMixin._dashboard)
    assert 'self.action("start")' not in source
    assert "self.core.ensure_ollama" not in source
    assert "Sterowanie procesami" in source
    assert "Stany usług — monitor" in source


def test_absent_optional_mcp_is_observed_without_gui_error_or_replay(window, monkeypatch) -> None:
    from tools.jazn_run_studio import probes

    def missing_gateway(_port: str) -> dict:
        raise ConnectionRefusedError("optional endpoint not running")

    monkeypatch.setattr(probes, "gateway", missing_gateway)
    previous_chat_state = window.chat_state.text()

    job = window.core.probe("gateway", observe_only=True)
    assert job.done.wait(5)
    assert job.state == "succeeded"
    assert job.error is None

    window.poll()
    assert window.chat_state.text() == previous_chat_state
    observed = window.workspace.observations.get("gateway", {})
    assert observed.get("endpoint_reachable") is False
    assert observed.get("ready") is False
    # No daemon/message submission and no auto-launch of optional MCP.
    assert window.core.chat is None
