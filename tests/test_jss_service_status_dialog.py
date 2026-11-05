"""Status window must never promote stale or incomplete evidence to green."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QWidget
from tools.jazn_run_studio.service_status_dialog import (
    MAX_OBSERVATION_AGE_SECONDS, ServiceStatusDialog, assess_service,
)


def _runtime_evidence() -> dict:
    return {
        "active_state": "active_trusted",
        "endpoint_reachable": True,
        "process_identity_confirmed": True,
        "endpoint_identity_matches": True,
        "heartbeat_fresh": True,
        "root_matches": True,
        "version_matches": True,
        "conversation_ready": True,
    }


def test_status_requires_live_identity_and_conversation_capability() -> None:
    good = _runtime_evidence()
    assert assess_service("server", good)[0] == "good"
    assert assess_service("runtime", good)[0] == "good"

    for missing in ("endpoint_reachable", "process_identity_confirmed",
                    "endpoint_identity_matches", "heartbeat_fresh",
                    "root_matches", "version_matches"):
        incomplete = {**good, missing: None}
        assert assess_service("server", incomplete)[0] != "good"
        assert assess_service("runtime", incomplete)[0] != "good"

    assert assess_service("runtime", {**good, "conversation_ready": False})[0] == "warn"
    assert assess_service("runtime", {**good, "active_state": "inactive"})[0] == "bad"
    assert assess_service("server", good, age_seconds=MAX_OBSERVATION_AGE_SECONDS + 1)[0] == "warn"
    assert assess_service("server", None)[0] == "warn"


def test_mcp_and_ollama_display_bounded_claims() -> None:
    assert assess_service("mcp", {"endpoint_reachable": True, "ready": True,
                                   "gateway_live": True})[0] == "good"
    assert assess_service("mcp", {"endpoint_reachable": True, "ready": True})[0] != "good"
    assert assess_service("ollama", {"endpoint_reachable": True,
                                     "selected_model_present": True})[0] == "warn"
    assert assess_service("ollama", {"endpoint_reachable": True,
                                     "selected_model_present": True,
                                     "generation_verified": True})[0] == "good"
    assert assess_service("ollama", None, failed=True)[0] == "bad"


def test_nonmodal_dialog_does_not_spawn_automatically() -> None:
    app = QApplication.instance() or QApplication([])
    assert app is not None

    class Host(QWidget):
        def __init__(self) -> None:
            super().__init__()
            self.refresh_count = 0

        def refresh_services(self) -> None:
            self.refresh_count += 1

        def guard(self, action) -> None:
            action()

    host = Host()
    panel = ServiceStatusDialog(host, lambda: host.guard(host.refresh_services))
    assert not panel.isModal()
    assert host.refresh_count == 0
    assert len(panel.indicators) == 4

    panel.observe("status", "evidence", _runtime_evidence())
    assert "Działa" in panel.indicators["runtime"][1].text()
    panel.observe("status", "state", {"state": "failed"})
    assert "Błąd" in panel.indicators["server"][1].text()

    panel.request_refresh()
    assert host.refresh_count == 1
    assert "Błąd" in panel.indicators["server"][1].text()
    assert "trwa sprawdzanie" in panel.indicators["server"][1].text()
    panel.close()
    host.close()


def test_refresh_keeps_last_good_evidence_and_uptime() -> None:
    app = QApplication.instance() or QApplication([])
    assert app is not None
    host = QWidget()
    panel = ServiceStatusDialog(host, lambda: None)
    panel.observe("status", "evidence", {**_runtime_evidence(),
                  "pid": 32812, "uptime_seconds": 3333.0})
    assert "Działa" in panel.indicators["server"][1].text()
    assert "00:55:33" in panel.indicators["server"][1].text()
    assert "32812" in panel.indicators["server"][1].text()
    panel.request_refresh()
    assert "Działa" in panel.indicators["server"][1].text()
    panel.close()
    host.close()


def test_model_listing_does_not_erase_fresh_generation_for_same_model() -> None:
    app = QApplication.instance() or QApplication([])
    assert app is not None
    host = QWidget()
    panel = ServiceStatusDialog(host, lambda: None)
    generated = {"service": "ollama", "endpoint_reachable": True,
                 "selected_model": "gemma3:latest",
                 "selected_model_present": True, "generation_verified": True}
    panel.observe("probe:ollama_generate", "probe", generated)
    assert "Działa" in panel.indicators["ollama"][1].text()
    panel.observe("probe:ollama", "probe", {**generated, "generation_verified": False})
    assert "Działa" in panel.indicators["ollama"][1].text()
    panel.observe("probe:ollama", "probe", {**generated, "selected_model": "other",
                  "generation_verified": False})
    assert "Niezweryfikowany" in panel.indicators["ollama"][1].text()
    panel.close()
    host.close()
