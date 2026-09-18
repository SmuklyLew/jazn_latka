from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from latka_jazn.config import JaznConfig
from latka_jazn.core import runtime_daemon
from latka_jazn.version import PACKAGE_VERSION_FULL


def _iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _install(
    monkeypatch: pytest.MonkeyPatch,
    root: Path,
    *,
    marker_pid: int,
    endpoint_pid: int,
    marker_instance: str,
    endpoint_instance: str,
) -> None:
    marker = {
        "pid": marker_pid,
        "daemon_instance_id": marker_instance,
        "active_root": str(root),
        "runtime_version": PACKAGE_VERSION_FULL,
        "last_heartbeat_at_utc": _iso(),
        "heartbeat_interval_seconds": 10,
        "timestamp_contract": {"trusted": False, "source": "local_machine"},
    }
    ping = {
        "daemon_pid": endpoint_pid,
        "daemon_instance_id": endpoint_instance,
        "runtime_process_active": True,
        "active_root": str(root),
        "runtime_version": PACKAGE_VERSION_FULL,
        "active_state": "active_trusted",
        "last_heartbeat_at_utc": _iso(),
        "heartbeat_interval_seconds": 10,
        "timestamp_trusted": False,
        "timestamp_contract": {"trusted": False, "source": "local_machine"},
    }
    monkeypatch.setattr(runtime_daemon, "resolve_active_runtime_marker_path", lambda *_a, **_k: root / "marker.json")
    monkeypatch.setattr(runtime_daemon, "read_json_file", lambda _path: marker)
    monkeypatch.setattr(
        runtime_daemon,
        "resolve_active_runtime_root",
        lambda *_a, **_k: SimpleNamespace(root=root, marker_found=True, marker_valid=True, source="marker", error=None),
    )
    monkeypatch.setattr(runtime_daemon, "pid_is_alive", lambda _pid: True)
    monkeypatch.setattr(runtime_daemon, "_probe_daemon_status", lambda *_a, **_k: (ping, None, "/ready"))
    monkeypatch.setattr(runtime_daemon, "verify_package_integrity_manifest", lambda _root: {"ok": True, "errors": []})
    monkeypatch.setattr(
        runtime_daemon,
        "read_source_provenance",
        lambda *_a, **_k: SimpleNamespace(to_dict=lambda: {"status": "verified_export_without_git_history", "limitations": []}),
    )


def test_instance_identity_allows_windows_redirector_pid_difference(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path.resolve()
    _install(
        monkeypatch,
        root,
        marker_pid=8456,
        endpoint_pid=10688,
        marker_instance="same-launch-id",
        endpoint_instance="same-launch-id",
    )

    result = runtime_daemon.status_daemon(JaznConfig(root=root))

    assert result["ok"] is True
    assert result["active_state"] == "active_trusted"
    assert result["endpoint_pid_matches"] is False
    assert result["endpoint_instance_matches"] is True
    assert result["endpoint_identity_basis"] == "daemon_instance_id+root"
    assert result["daemon_instance_id"] == "same-launch-id"


def test_instance_identity_mismatch_fails_closed_even_if_pid_matches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path.resolve()
    _install(
        monkeypatch,
        root,
        marker_pid=10688,
        endpoint_pid=10688,
        marker_instance="launch-a",
        endpoint_instance="launch-b",
    )

    result = runtime_daemon.status_daemon(JaznConfig(root=root))

    assert result["ok"] is False
    assert result["active_state"] == "inactive"
    assert result["endpoint_pid_matches"] is True
    assert result["endpoint_instance_matches"] is False
    assert result["active_state_reason"] == "endpoint_daemon_instance_mismatch"
