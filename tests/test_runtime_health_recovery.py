from __future__ import annotations

from pathlib import Path
import threading

from latka_jazn.core import runtime_supervisor
from latka_jazn.core.runtime_health import DaemonHealthClass, classify_daemon_health


def test_health_classifier_recovers_stale_confirmed_daemon() -> None:
    result = classify_daemon_health(
        {
            "active_state": "active_degraded",
            "active_state_reason": "endpoint_identity_confirmed_heartbeat_stale",
            "endpoint_reachable": True,
            "endpoint_identity_matches": True,
            "process_identity_confirmed": True,
            "heartbeat_is_fresh": False,
        }
    )
    assert result.classification is DaemonHealthClass.RECOVER


def test_health_classifier_fails_closed_on_identity_mismatch() -> None:
    result = classify_daemon_health(
        {
            "active_state": "inactive",
            "active_state_reason": "endpoint_daemon_instance_mismatch",
            "endpoint_reachable": True,
            "endpoint_identity_matches": False,
            "process_identity_confirmed": False,
        }
    )
    assert result.classification is DaemonHealthClass.IDENTITY_AMBIGUOUS


def test_health_classifier_keeps_verified_runtime_without_time_based_restart() -> None:
    result = classify_daemon_health(
        {
            "active_state": "active_trusted",
            "active_state_reason": "endpoint_runtime_identity_confirmed",
            "endpoint_reachable": True,
            "endpoint_identity_matches": True,
            "process_identity_confirmed": True,
            "heartbeat_is_fresh": True,
        }
    )
    assert result.classification is DaemonHealthClass.HEALTHY


def test_supervisor_uses_canonical_restart_for_recoverable_degradation(
    tmp_path: Path, monkeypatch
) -> None:
    root = tmp_path / "runtime"
    root.mkdir()
    stop_event = threading.Event()
    calls: list[str] = []

    monkeypatch.setattr(runtime_supervisor, "_claim_supervisor_pid", lambda _root: (True, None))
    monkeypatch.setattr(
        runtime_supervisor,
        "_cheap_daemon_liveness",
        lambda *_args, **_kwargs: {"ok": False, "liveness_ok": False},
    )
    monkeypatch.setattr(
        runtime_supervisor,
        "status_daemon",
        lambda *_args, **_kwargs: {
            "active_state": "active_degraded",
            "active_state_reason": "endpoint_identity_confirmed_heartbeat_stale",
            "endpoint_reachable": True,
            "endpoint_identity_matches": True,
            "process_identity_confirmed": True,
            "heartbeat_is_fresh": False,
        },
    )

    def restart(*_args, **_kwargs):
        calls.append("restart")
        stop_event.set()
        return {"ok": True, "pid": 123, "daemon_instance_id": "new"}

    monkeypatch.setattr(runtime_supervisor, "restart_daemon", restart)
    monkeypatch.setattr(runtime_supervisor, "_write_json_atomic", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        runtime_supervisor,
        "supervisor_pid_path",
        lambda _root: tmp_path / "missing-supervisor.pid",
    )

    code = runtime_supervisor.run_supervisor(
        root,
        check_interval_seconds=0.01,
        startup_timeout_seconds=0.1,
        stop_event=stop_event,
    )
    assert code == 0
    assert calls == ["restart"]


def test_supervisor_does_not_restart_identity_ambiguous_process(
    tmp_path: Path, monkeypatch
) -> None:
    root = tmp_path / "runtime"
    root.mkdir()
    stop_event = threading.Event()
    calls: list[str] = []

    monkeypatch.setattr(runtime_supervisor, "_claim_supervisor_pid", lambda _root: (True, None))
    monkeypatch.setattr(
        runtime_supervisor,
        "_cheap_daemon_liveness",
        lambda *_args, **_kwargs: {"ok": False, "liveness_ok": False},
    )
    monkeypatch.setattr(
        runtime_supervisor,
        "status_daemon",
        lambda *_args, **_kwargs: {
            "active_state": "inactive",
            "active_state_reason": "endpoint_daemon_instance_mismatch",
            "endpoint_reachable": True,
            "endpoint_identity_matches": False,
            "process_identity_confirmed": False,
        },
    )
    monkeypatch.setattr(
        runtime_supervisor,
        "restart_daemon",
        lambda *_args, **_kwargs: calls.append("restart") or {"ok": True},
    )
    monkeypatch.setattr(runtime_supervisor, "_write_json_atomic", lambda *_args, **_kwargs: stop_event.set())
    monkeypatch.setattr(
        runtime_supervisor,
        "supervisor_pid_path",
        lambda _root: tmp_path / "missing-supervisor.pid",
    )
    monkeypatch.setattr(runtime_supervisor, "bounded_restart_backoff_seconds", lambda *_a, **_k: 0.01)

    code = runtime_supervisor.run_supervisor(
        root,
        check_interval_seconds=0.01,
        startup_timeout_seconds=0.1,
        stop_event=stop_event,
    )
    assert code == 0
    assert calls == []
