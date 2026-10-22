"""Regression: live old-version daemons cannot be reused after release upgrades.

All status data is synthetic. No real daemon is started, killed, or restarted.
"""
from __future__ import annotations

from pathlib import Path
import threading

import pytest

from latka_jazn.core import runtime_supervisor
from latka_jazn.version import PACKAGE_VERSION_FULL


@pytest.mark.parametrize(
    ("cheap_version_matches", "full_version", "expected_state"),
    [
        (False, "16.3.25.5.116.0.34.41-first-run-memory-evidence",
         "daemon_version_mismatch_operator_restart_required"),
        (None, "16.3.25.5.116.0.34.41-first-run-memory-evidence",
         "daemon_version_mismatch_operator_restart_required"),
        (None, None, "daemon_version_unverified_operator_check_required"),
    ],
)
def test_supervisor_never_reuses_healthy_old_or_unverified_daemon(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    cheap_version_matches: bool | None,
    full_version: str | None,
    expected_state: str,
) -> None:
    root = tmp_path / "system"
    root.mkdir()
    stop_event = threading.Event()
    saved: list[dict[str, object]] = []
    restarts: list[str] = []

    monkeypatch.setattr(runtime_supervisor, "_claim_supervisor_pid", lambda _root: (True, None))
    monkeypatch.setattr(
        runtime_supervisor, "_cheap_daemon_liveness",
        lambda *_a, **_kw: {"ok": False, "liveness_ok": True,
                             "runtime_version_matches": cheap_version_matches},
    )
    monkeypatch.setattr(
        runtime_supervisor, "status_daemon",
        lambda *_a, **_kw: {
            "active_state": "active_trusted",
            "active_state_reason": "endpoint_runtime_identity_confirmed",
            "endpoint_reachable": True,
            "endpoint_identity_matches": True,
            "process_identity_confirmed": True,
            "heartbeat_is_fresh": True,
            "ping": {"runtime_version": full_version} if full_version else None,
        },
    )
    monkeypatch.setattr(
        runtime_supervisor, "restart_daemon",
        lambda *_a, **_kw: restarts.append("restart") or {"ok": True},
    )
    monkeypatch.setattr(runtime_supervisor, "bounded_restart_backoff_seconds", lambda *_a, **_kw: 0.01)
    monkeypatch.setattr(runtime_supervisor, "supervisor_pid_path",
                        lambda _root: root / "missing-supervisor.pid")

    def capture(_path: Path, data: dict[str, object]) -> None:
        saved.append(data)
        if data.get("state") == expected_state:
            stop_event.set()

    monkeypatch.setattr(runtime_supervisor, "_write_json_atomic", capture)
    code = runtime_supervisor.run_supervisor(root, stop_event=stop_event, check_interval_seconds=0.01)
    assert code == 0
    assert restarts == []
    blocked = next(x for x in saved if x.get("state") == expected_state)
    evidence = blocked["last_liveness"]
    assert isinstance(evidence, dict)
    assert evidence["version_gate"]["ok"] is False
    assert evidence["version_gate"]["expected_runtime_version"] == PACKAGE_VERSION_FULL
    last_start = blocked["last_start"]
    assert isinstance(last_start, dict)
    assert last_start["error_code"] == expected_state


def test_supervisor_can_reuse_same_version_only_after_full_verification(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "system"
    root.mkdir()
    stop_event = threading.Event()
    states: list[str] = []
    restarts: list[str] = []
    monkeypatch.setattr(runtime_supervisor, "_claim_supervisor_pid", lambda _root: (True, None))
    monkeypatch.setattr(runtime_supervisor, "_cheap_daemon_liveness",
                        lambda *_a, **_kw: {"ok": False, "liveness_ok": False})
    monkeypatch.setattr(runtime_supervisor, "status_daemon",
                        lambda *_a, **_kw: {
                            "active_state": "active_trusted",
                            "active_state_reason": "endpoint_runtime_identity_confirmed",
                            "endpoint_reachable": True,
                            "endpoint_identity_matches": True,
                            "process_identity_confirmed": True,
                            "heartbeat_is_fresh": True,
                            "ping": {"runtime_version": PACKAGE_VERSION_FULL},
                        })
    monkeypatch.setattr(runtime_supervisor, "restart_daemon",
                        lambda *_a, **_kw: restarts.append("restart") or {"ok": True})
    monkeypatch.setattr(runtime_supervisor, "supervisor_pid_path",
                        lambda _root: root / "missing-supervisor.pid")

    def capture(_path: Path, data: dict[str, object]) -> None:
        states.append(str(data["state"]))
        if data["state"] == "daemon_live_after_full_probe":
            stop_event.set()

    monkeypatch.setattr(runtime_supervisor, "_write_json_atomic", capture)
    code = runtime_supervisor.run_supervisor(root, stop_event=stop_event, check_interval_seconds=0.01)
    assert code == 0
    assert restarts == []
    assert "daemon_live_after_full_probe" in states
