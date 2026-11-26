"""Synthetic Stage 05 F08: historical heartbeat is not evidence of liveness."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from latka_jazn.config import JaznConfig
from latka_jazn.core import runtime_daemon as daemon


def _setup(
    root: Path, monkeypatch: pytest.MonkeyPatch, *,
    stopped: bool = True, pid_alive: bool = False, endpoint: bool = False,
    age: int = 0, integrity: bool = True,
) -> None:
    now = datetime.now(timezone.utc)
    marker: dict[str, Any] = {
        "daemon_pid": 1234, "daemon_instance_id": "synthetic-old-instance",
        "active_root": str(root), "heartbeat_interval_seconds": 10,
        "last_heartbeat_at_utc": (now - timedelta(seconds=age)).isoformat(),
        "timestamp_contract": {"trusted": False, "source": "local_machine"},
    }
    if stopped:
        marker.update(
            daemon_status=daemon.DAEMON_MARKER_STATUS_STOPPED,
            active_state="inactive", runtime_process_active=False,
            stopped_at_utc=now.isoformat(),
        )
    ping = {
        "daemon_pid": 4321, "daemon_instance_id": "synthetic-other-instance",
        "active_root": str(root), "runtime_process_active": True,
        "heartbeat_interval_seconds": 10, "last_heartbeat_at_utc": now.isoformat(),
    } if endpoint else None
    monkeypatch.setattr(daemon, "resolve_active_runtime_marker_path", lambda *_a, **_k: root / "marker.json")
    monkeypatch.setattr(daemon, "read_json_file", lambda *_a, **_k: marker)
    monkeypatch.setattr(daemon, "resolve_active_runtime_root", lambda *_a, **_k: SimpleNamespace(
        root=root, marker_found=True, marker_valid=True, source="marker", error=None,
    ))
    monkeypatch.setattr(daemon, "verify_package_integrity_manifest", lambda *_a, **_k: {"ok": integrity})
    monkeypatch.setattr(daemon, "read_source_provenance", lambda *_a, **_k: SimpleNamespace(
        to_dict=lambda: {"status": "verified_export_without_git_history"},
    ))
    monkeypatch.setattr(daemon, "pid_is_alive", lambda *_a, **_k: pid_alive)
    monkeypatch.setattr(daemon, "process_fingerprint_matches", lambda *_a, **_k: None)
    monkeypatch.setattr(daemon, "_probe_daemon_status", lambda *_a, **_k: (
        ping, None if ping else "synthetic endpoint unavailable", "/live" if ping else None,
    ))


@pytest.mark.parametrize("age", [0, 3600])
def test_confirmed_stop_is_inactive_without_repair_advice(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, age: int,
) -> None:
    _setup(tmp_path, monkeypatch, age=age)
    status = daemon.status_daemon(JaznConfig(root=tmp_path))
    assert status["active_state"] == "inactive"
    assert status["ok"] is False
    assert status["pid_alive"] is False
    assert status["endpoint_reachable"] is False
    assert status["stopped_confirmed"] is True
    assert status["active_state_reason"] == "daemon_stopped_confirmed"
    assert status["observation_state"] == "stopped_verified"
    assert status["readiness_state"] == "not_ready"
    assert status["heartbeat_fresh"] is False
    assert status["marker_heartbeat_fresh"] is False
    assert status["marker_heartbeat_age_seconds"] is not None
    assert status["recommended_repair"] is None


def test_stopped_marker_does_not_override_live_pid_or_foreign_endpoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _setup(tmp_path, monkeypatch, pid_alive=True)
    live_pid = daemon.status_daemon(JaznConfig(root=tmp_path))
    assert live_pid["stopped_confirmed"] is False
    assert live_pid["active_state"] == "active_degraded"
    assert live_pid["recommended_repair"]["kind"] == "endpoint_unreachable"
    _setup(tmp_path, monkeypatch, endpoint=True)
    foreign = daemon.status_daemon(JaznConfig(root=tmp_path))
    assert foreign["stopped_confirmed"] is False
    assert foreign["active_state_reason"] == "endpoint_daemon_instance_mismatch"
    assert foreign["recommended_repair"]["kind"] == "daemon_instance_mismatch"


def test_read_only_snapshot_cannot_confirm_stop_or_suggest_endpoint_repair(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _setup(tmp_path, monkeypatch)
    def unexpected_probe(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("snapshot must not probe")
    monkeypatch.setattr(daemon, "_probe_daemon_status", unexpected_probe)
    status = daemon.status_daemon(JaznConfig(root=tmp_path), probe_endpoint=False)
    assert status["stopped_confirmed"] is False
    assert status["observation_state"] == "endpoint_not_probed"
    assert status["recommended_repair"] is None


def test_dead_pid_with_fresh_history_without_stop_marker_is_not_a_confirmed_stop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _setup(tmp_path, monkeypatch, stopped=False)
    status = daemon.status_daemon(JaznConfig(root=tmp_path))
    assert status["active_state"] == "inactive"
    assert status["stopped_confirmed"] is False
    assert status["recommended_repair"] is None


def test_unverified_package_cannot_confirm_stop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _setup(tmp_path, monkeypatch, integrity=False)
    status = daemon.status_daemon(JaznConfig(root=tmp_path))
    assert status["stopped_confirmed"] is False
    assert status["active_state_reason"] == "package_integrity_verification_failed"
