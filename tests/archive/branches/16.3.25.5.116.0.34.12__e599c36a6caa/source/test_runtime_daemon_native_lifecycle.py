from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import json
import os

from latka_jazn.config import JaznConfig
from latka_jazn.core import runtime_daemon
from latka_jazn.core import runtime_daemon_lifecycle_hotfix as hotfix
from latka_jazn.core.process_identity import PROCESS_FINGERPRINT_SCHEMA_VERSION


def _fingerprint(pid: int, token: str) -> dict[str, object]:
    return {
        "schema_version": PROCESS_FINGERPRINT_SCHEMA_VERSION,
        "pid": pid,
        "platform": os.name,
        "available": True,
        "identity_token": token,
        "state": "observed",
    }


def test_native_daemon_lifecycle_disables_monkeypatch_install(
    monkeypatch,
) -> None:
    start = runtime_daemon.start_daemon
    status = runtime_daemon.status_daemon
    stop = runtime_daemon.stop_daemon
    run = runtime_daemon.run_daemon
    monkeypatch.setattr(hotfix, "_INSTALLED", False)
    hotfix.install_runtime_daemon_lifecycle_hotfix()
    assert runtime_daemon._NATIVE_DAEMON_LIFECYCLE_IDENTITY_V2 is True
    assert runtime_daemon.start_daemon is start
    assert runtime_daemon.status_daemon is status
    assert runtime_daemon.stop_daemon is stop
    assert runtime_daemon.run_daemon is run


def test_native_status_rejects_reused_pid_without_endpoint_identity(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = tmp_path / "runtime"
    root.mkdir()
    marker_path = root / "marker.json"
    marker = {
        "active_root": str(root),
        "daemon_pid": 4242,
        "daemon_instance_id": "old-instance",
        "last_heartbeat_at_utc": "2099-01-01T00:00:00+00:00",
        "heartbeat_interval_seconds": 30.0,
        "process_fingerprint": _fingerprint(4242, "old-process"),
    }
    marker_path.write_text(json.dumps(marker), encoding="utf-8")

    monkeypatch.setattr(
        runtime_daemon,
        "resolve_active_runtime_marker_path",
        lambda *_a, **_k: marker_path,
    )
    monkeypatch.setattr(
        runtime_daemon,
        "read_json_file",
        lambda _path: marker,
    )
    monkeypatch.setattr(
        runtime_daemon,
        "resolve_active_runtime_root",
        lambda *_a, **_k: SimpleNamespace(
            root=root,
            marker_found=True,
            marker_valid=True,
            source="active_marker",
            error=None,
        ),
    )
    monkeypatch.setattr(
        runtime_daemon,
        "verify_package_integrity_manifest",
        lambda _root: {"ok": True},
    )
    monkeypatch.setattr(
        runtime_daemon,
        "read_source_provenance",
        lambda *_a, **_k: SimpleNamespace(
            to_dict=lambda: {
                "status": "verified_export_without_git_history"
            }
        ),
    )
    monkeypatch.setattr(
        runtime_daemon,
        "read_runtime_version_from_version_py",
        lambda *_a, **_k: "16.3.25.5.87.5-test",
    )
    monkeypatch.setattr(runtime_daemon, "pid_is_alive", lambda _pid: True)
    monkeypatch.setattr(
        runtime_daemon,
        "process_fingerprint",
        lambda pid, **_kwargs: _fingerprint(
            int(pid or 0),
            "reused-process",
        ),
    )
    monkeypatch.setattr(
        runtime_daemon,
        "_probe_daemon_status",
        lambda *_a, **_k: (None, "connection refused", None),
    )

    result = runtime_daemon.status_daemon(
        JaznConfig(root=root),
        probe_endpoint=True,
    )
    assert result["pid_alive_os_probe"] is True
    assert result["pid_alive_os_identity"] is False
    assert result["process_fingerprint_match"] is False
    assert result["pid_alive"] is False
    assert result["process_state"] == "pid_reused"
    assert result["identity_state"] == "process_fingerprint_mismatch"
    assert result["active_state"] == "inactive"
    assert (
        result["active_state_reason"]
        == "pid_reused_process_fingerprint_mismatch"
    )


def test_native_runtime_versions_bind_subject_root(
    monkeypatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "subject"
    root.mkdir()
    monkeypatch.setattr(
        runtime_daemon,
        "read_runtime_version_from_version_py",
        lambda observed_root, **_kwargs: (
            "99.1-subject"
            if Path(observed_root) == root
            else "wrong"
        ),
    )
    base, full = runtime_daemon._runtime_versions(root, "fallback")
    assert base == "99.1"
    assert full == "99.1-subject"
