from __future__ import annotations

from pathlib import Path

from latka_jazn.cli_commands import diagnostics
from latka_jazn.config import JaznConfig
from latka_jazn.core.rest_cycle_controller import RestCycleController


def test_rest_capability_resolves_ready_endpoint_evidence_not_live_top_level() -> None:
    daemon = {
        "active_state": "active_trusted",
        "readiness": {
            "ok": True,
            "endpoint": "/ready",
            "rest_cycle_status": {
                "enabled": True,
                "state": "waiting_for_idle",
                "rest_scheduler_ready": True,
                "rest_scheduler_running": True,
            },
        },
    }

    status, source = diagnostics._daemon_subsystem_status(daemon, "rest_cycle_status")
    ready, running, state = diagnostics._rest_scheduler_capability(status)

    assert source == "daemon.readiness.rest_cycle_status"
    assert ready is True
    assert running is True
    assert state == "waiting_for_idle"


def test_rest_capability_fails_closed_without_live_scheduler_thread() -> None:
    status = {
        "enabled": True,
        "state": "initialized",
        "rest_scheduler_ready": True,
        "rest_scheduler_running": False,
    }
    ready, running, state = diagnostics._rest_scheduler_capability(status)

    assert ready is False
    assert running is False
    assert state == "initialized"


def test_rest_capability_has_explicit_state_when_readiness_evidence_missing() -> None:
    ready, running, state = diagnostics._rest_scheduler_capability({})
    assert ready is False
    assert running is False
    assert state == "readiness_evidence_unavailable"


def test_controller_reports_ready_only_after_scheduler_thread_starts(tmp_path: Path) -> None:
    cfg = JaznConfig(root=tmp_path, rest_cycle_enabled=True, rest_poll_seconds=0.1)
    controller = RestCycleController(cfg)
    try:
        before = controller.status_payload()
        assert before["state"] == "initialized"
        assert before["rest_scheduler_running"] is False
        assert before["rest_scheduler_ready"] is False

        controller.start()
        after = controller.status_payload()
        assert after["state"] == "waiting_for_idle"
        assert after["rest_scheduler_running"] is True
        assert after["rest_scheduler_ready"] is True

        controller.stop()
        stopped = controller.status_payload()
        assert stopped["state"] == "stopped"
        assert stopped["rest_scheduler_running"] is False
        assert stopped["rest_scheduler_ready"] is False
    finally:
        controller.close()
