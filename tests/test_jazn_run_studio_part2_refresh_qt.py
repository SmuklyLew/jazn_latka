"""Explicit service refresh requests the one read-only Jaźń Monitor snapshot."""
from __future__ import annotations

import pytest

pytest.importorskip("PySide6")
from tests.test_jazn_run_studio_layout import window
from tools.jazn_run_studio.core import ACTION_BY_KEY, StudioError


def test_refresh_uses_only_read_only_status_and_probe_contracts(window, monkeypatch):
    observed: list[str] = []

    class Monitor:
        def refresh(self):
            observed.append("monitor:refresh")

    monkeypatch.setattr(window, "_ensure_monitor_window", lambda: Monitor())
    monkeypatch.setattr(window.core, "start_action",
                        lambda _key: pytest.fail("read-only refresh must not start controller actions"))
    monkeypatch.setattr(window.core, "probe",
                        lambda _key: pytest.fail("JSS must not create a second probe feed"))
    window.refresh_services()
    assert observed == ["monitor:refresh"]
    assert not ACTION_BY_KEY["status"].mutates
    assert not ACTION_BY_KEY["supervisor"].mutates
    assert "Nie sprawdzono" in window.dashboard_statuses["cloudflare"].text()


def test_refresh_includes_configured_cloudflare_observation(window, monkeypatch):
    from dataclasses import replace
    window.core.settings = replace(window.core.settings, cloudflare_url="https://test.workers.dev")
    observed: list[str] = []

    class Monitor:
        def refresh(self):
            observed.append("monitor:refresh")

    monkeypatch.setattr(window, "_ensure_monitor_window", lambda: Monitor())
    monkeypatch.setattr(window.core, "probe",
                        lambda _key: pytest.fail("configured HTTPS is not an authenticated probe"))
    window.refresh_services()
    assert observed == ["monitor:refresh"]
    assert "Nie sprawdzono" in window.dashboard_statuses["cloudflare"].text()


def test_refresh_propagates_failure_without_making_up_ready_state(window, monkeypatch):
    def unavailable():
        raise StudioError("no available monitor")

    monkeypatch.setattr(window, "_ensure_monitor_window", unavailable)
    with pytest.raises(StudioError, match="no available monitor"):
        window.refresh_services()
    assert "Nie sprawdzono" in window.dashboard_statuses["ollama"].text()
