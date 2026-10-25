"""Explicit service refresh dispatches read-only probes without starting a daemon."""
from __future__ import annotations

import pytest

pytest.importorskip("PySide6")
from tests.test_jazn_run_studio_layout import window
from tools.jazn_run_studio.core import StudioError


def test_refresh_uses_only_read_only_status_and_probe_contracts(window, monkeypatch):
    observed: list[str] = []
    monkeypatch.setattr(window.core, "start_action", lambda key: observed.append("action:" + key))
    monkeypatch.setattr(window.core, "probe", lambda key: observed.append("probe:" + key))
    window.refresh_services()
    assert observed == ["action:status", "probe:ollama", "probe:gateway"]
    assert "Nie skonfigurowano" in window.dashboard_statuses["cloudflare"].text()


def test_refresh_includes_configured_cloudflare_observation(window, monkeypatch):
    from dataclasses import replace
    window.core.settings = replace(window.core.settings, cloudflare_url="https://test.workers.dev")
    observed: list[str] = []
    monkeypatch.setattr(window.core, "start_action", lambda key: observed.append("action:" + key))
    monkeypatch.setattr(window.core, "probe", lambda key: observed.append("probe:" + key))
    window.refresh_services()
    assert observed[-1] == "probe:cloudflare"


def test_refresh_propagates_failure_without_making_up_ready_state(window, monkeypatch):
    monkeypatch.setattr(window.core, "start_action", lambda _key: None)

    def missing(_key):
        raise StudioError("no available model")

    monkeypatch.setattr(window.core, "probe", missing)
    with pytest.raises(StudioError, match="no available model"):
        window.refresh_services()
    assert "Nie sprawdzono" in window.dashboard_statuses["ollama"].text()
