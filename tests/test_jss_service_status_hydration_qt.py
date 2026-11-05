"""JSS status dialog rehydrates already observed evidence without new probes."""
from __future__ import annotations

import time

import pytest

pytest.importorskip("PySide6")
from tests.test_jazn_run_studio_layout import window


def _ready() -> dict[str, object]:
    return {
        "active_state": "active_trusted", "endpoint_reachable": True,
        "process_identity_confirmed": True, "endpoint_identity_matches": True,
        "heartbeat_fresh": True, "root_matches": True,
        "version_matches": True, "conversation_ready": True,
        "pid": 2552, "uptime_seconds": 434.312069,
    }


def test_open_after_probes_uses_same_session_evidence_without_rechecking(
    window, monkeypatch: pytest.MonkeyPatch,
) -> None:
    def no_probe(*_args, **_kwargs):
        raise AssertionError("Opening status dialog must be read only")
    monkeypatch.setattr(window.core, "start_action", no_probe)
    monkeypatch.setattr(window.core, "probe", no_probe)
    window.core.emit("status", "evidence", _ready())
    window.core.emit("probe:ollama_generate", "probe", {
        "service": "ollama", "endpoint_reachable": True,
        "selected_model": "gemma3:latest", "selected_model_present": True,
        "generation_verified": True,
    })
    window.poll()
    assert window.service_status_dialog is None
    window.open_service_status()
    dialog = window.service_status_dialog
    assert dialog is not None
    assert "Działa" in dialog.indicators["server"][1].text()
    assert "2552" in dialog.indicators["server"][1].text()
    assert "Działa" in dialog.indicators["runtime"][1].text()
    assert "Działa" in dialog.indicators["ollama"][1].text()
    dialog.close()
    window.open_service_status()
    assert window.service_status_dialog is dialog
    assert "Działa" in dialog.indicators["server"][1].text()
    dialog.close()


def test_hydration_preserves_observation_age_and_does_not_forge_green(window) -> None:
    window.service_status_history[("status", "evidence")] = (
        time.monotonic() - 60.0, _ready()
    )
    window.open_service_status()
    dialog = window.service_status_dialog
    assert dialog is not None
    assert "Wynik nieaktualny" in dialog.indicators["server"][1].text()
    assert "Wynik nieaktualny" in dialog.indicators["runtime"][1].text()
    dialog.close()


def test_failed_status_precedes_newer_verified_evidence(window) -> None:
    window.core.emit("status", "state", {"state": "failed", "error": "probe_failure"})
    window.core.emit("status", "evidence", _ready())
    window.poll()
    window.open_service_status()
    dialog = window.service_status_dialog
    assert dialog is not None
    assert "Działa" in dialog.indicators["server"][1].text()
    dialog.close()
