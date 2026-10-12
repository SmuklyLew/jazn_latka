from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import json
import os
import subprocess
import sys

from latka_jazn.config import JaznConfig
from latka_jazn.core import runtime_daemon, runtime_lifecycle
from latka_jazn.core.runtime_daemon_lifecycle_hotfix import (
    PROCESS_FINGERPRINT_SCHEMA_VERSION,
    _cleanup_owned_pid_file,
    _terminate_spawned_process,
    process_fingerprint,
    process_fingerprint_matches,
)


def _status(root: Path, *, active: bool) -> dict:
    return {
        "active_state": "active_trusted" if active else "inactive",
        "endpoint_reachable": active,
        "endpoint_root_matches": active,
        "endpoint_identity_matches": active,
        "process_identity_confirmed": active,
        "pid_alive_os_probe": active,
        "process_fingerprint_match": True if active else None,
        "active_root": str(root),
        "resolved_active_root": str(root),
        "subject_runtime_root": str(root),
        "requested_runtime_root": str(root),
        "marker": {"active_root": str(root)},
    }


def _preflight(root: Path) -> dict:
    return {
        "ok": True,
        "root": str(root),
        "start_file": str(root / "run.py"),
        "package_integrity_verification": {"ok": True},
        "source_provenance": {"status": "verified_export_without_git_history"},
        "source_provenance_verified": True,
        "error_code": None,
    }


def test_process_fingerprint_binds_pid_to_start_identity() -> None:
    observed = process_fingerprint(os.getpid(), pid_is_alive=runtime_daemon.pid_is_alive)
    assert observed["pid"] == os.getpid()
    assert observed["state"] in {"observed", "alive_without_stable_token"}
    if observed["available"] is True:
        assert process_fingerprint_matches(observed, dict(observed)) is True
        forged = dict(observed)
        forged["identity_token"] = str(observed["identity_token"]) + "-other"
        assert process_fingerprint_matches(observed, forged) is False


def test_spawn_cleanup_terminates_owned_child() -> None:
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    try:
        result = _terminate_spawned_process(proc, grace_seconds=0.5)
        assert result["attempted"] is True
        assert result["terminated"] is True
        assert proc.poll() is not None
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=2)


def test_owned_pid_file_cleanup_refuses_foreign_pid(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("JAZN_RUNTIME_WORKSPACE_DIR", str(tmp_path / "workspace"))
    root = tmp_path / "runtime"
    root.mkdir()
    pid_path = runtime_daemon.daemon_pid_path(root)
    pid_path.parent.mkdir(parents=True, exist_ok=True)
    pid_path.write_text("222", encoding="utf-8")
    refused = _cleanup_owned_pid_file(runtime_daemon, root, 111)
    assert refused["owned"] is False
    assert pid_path.exists()
    removed = _cleanup_owned_pid_file(runtime_daemon, root, 222)
    assert removed["owned"] is True
    assert removed["removed"] is True
    assert not pid_path.exists()


def test_reload_stop_failure_never_switches_marker_or_starts_target(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / "workspace"
    monkeypatch.setenv("JAZN_RUNTIME_WORKSPACE_DIR", str(workspace))
    old = tmp_path / "old"
    target = tmp_path / "target"
    old.mkdir(); target.mkdir()
    marker = workspace / "JAZN_ACTIVE_RUNTIME.json"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(json.dumps({"active_root": str(old)}), encoding="utf-8")

    monkeypatch.setattr(runtime_lifecycle, "_target_preflight", lambda _root: _preflight(target))
    monkeypatch.setattr(runtime_lifecycle, "resolve_active_runtime_root", lambda *_a, **_k: SimpleNamespace(marker_found=True, marker_valid=True, root=old, error=None))
    monkeypatch.setattr(runtime_lifecycle, "status_daemon", lambda *_a, **_k: _status(old, active=True))
    monkeypatch.setattr(runtime_lifecycle, "stop_daemon", lambda *_a, **_k: {"ok": False, "error_code": "daemon_stop_timeout"})

    calls = {"marker": 0, "start": 0}
    monkeypatch.setattr(runtime_lifecycle, "write_active_runtime_marker", lambda *_a, **_k: calls.__setitem__("marker", calls["marker"] + 1))
    monkeypatch.setattr(runtime_lifecycle, "start_daemon", lambda *_a, **_k: calls.__setitem__("start", calls["start"] + 1))

    result = runtime_lifecycle.reload_daemon(JaznConfig(root=old), target_root=target)
    assert result["ok"] is False
    assert result["state"] == "stop_failed_no_handoff"
    assert calls == {"marker": 0, "start": 0}


def test_reload_commits_target_after_confirmed_stop(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / "workspace"
    monkeypatch.setenv("JAZN_RUNTIME_WORKSPACE_DIR", str(workspace))
    old = tmp_path / "old"
    target = tmp_path / "target"
    old.mkdir(); target.mkdir()
    marker = workspace / "JAZN_ACTIVE_RUNTIME.json"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(json.dumps({"active_root": str(old)}), encoding="utf-8")

    monkeypatch.setattr(runtime_lifecycle, "_target_preflight", lambda _root: _preflight(target))
    monkeypatch.setattr(runtime_lifecycle, "resolve_active_runtime_root", lambda *_a, **_k: SimpleNamespace(marker_found=True, marker_valid=True, root=old, error=None))
    statuses = iter([_status(old, active=True), _status(target, active=True)])
    monkeypatch.setattr(runtime_lifecycle, "status_daemon", lambda *_a, **_k: next(statuses))
    monkeypatch.setattr(runtime_lifecycle, "stop_daemon", lambda *_a, **_k: {"ok": True, "stopped": True})
    monkeypatch.setattr(runtime_lifecycle, "write_active_runtime_marker", lambda root, **_k: {"active_root": str(root)})
    monkeypatch.setattr(runtime_lifecycle, "start_daemon", lambda *_a, **_k: {"ok": True, "started": True})

    result = runtime_lifecycle.reload_daemon(JaznConfig(root=old), target_root=target)
    assert result["ok"] is True
    assert result["state"] == "handoff_committed"
    assert result["after"]["active_root"] == str(target)


def test_reload_start_failure_restores_marker_and_restarts_previous_root(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / "workspace"
    monkeypatch.setenv("JAZN_RUNTIME_WORKSPACE_DIR", str(workspace))
    old = tmp_path / "old"
    target = tmp_path / "target"
    old.mkdir(); target.mkdir()
    marker = workspace / "JAZN_ACTIVE_RUNTIME.json"
    marker.parent.mkdir(parents=True, exist_ok=True)
    original = json.dumps({"active_root": str(old), "sentinel": "keep"}, sort_keys=True).encode("utf-8")
    marker.write_bytes(original)

    monkeypatch.setattr(runtime_lifecycle, "_target_preflight", lambda _root: _preflight(target))
    monkeypatch.setattr(runtime_lifecycle, "resolve_active_runtime_root", lambda *_a, **_k: SimpleNamespace(marker_found=True, marker_valid=True, root=old, error=None))
    statuses = iter([_status(old, active=True), _status(old, active=True)])
    monkeypatch.setattr(runtime_lifecycle, "status_daemon", lambda *_a, **_k: next(statuses))
    monkeypatch.setattr(runtime_lifecycle, "stop_daemon", lambda *_a, **_k: {"ok": True, "stopped": True})

    def write_target(root: Path, **_kwargs):
        marker.write_text(json.dumps({"active_root": str(root), "target": True}), encoding="utf-8")
        return {"active_root": str(root)}

    monkeypatch.setattr(runtime_lifecycle, "write_active_runtime_marker", write_target)
    starts: list[Path] = []

    def start(config: JaznConfig, **_kwargs):
        root = Path(config.root)
        starts.append(root)
        return {"ok": root == old, "started": root == old, "error_code": None if root == old else "daemon_startup_not_ready"}

    monkeypatch.setattr(runtime_lifecycle, "start_daemon", start)

    result = runtime_lifecycle.reload_daemon(JaznConfig(root=old), target_root=target)
    assert result["ok"] is False
    assert result["state"] == "target_start_failed_rolled_back"
    assert starts == [target, old]
    assert marker.read_bytes() == original
    assert result["rollback"]["ok"] is True


def test_reload_operator_exposes_explicit_target_root() -> None:
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, str(root / "run.py"), "reload", "--help"],
        cwd=str(root), text=True, capture_output=True, timeout=20, check=False,
    )
    assert result.returncode == 0
    assert "--target-root" in result.stdout


def test_status_rejects_reused_pid_when_marker_fingerprint_differs(tmp_path: Path, monkeypatch) -> None:
    from datetime import datetime, timezone

    monkeypatch.setenv("JAZN_RUNTIME_WORKSPACE_DIR", str(tmp_path / "workspace"))
    root = tmp_path / "runtime"
    root.mkdir()
    marker_path = runtime_daemon.resolve_active_runtime_marker_path(root, None)
    marker_path.parent.mkdir(parents=True, exist_ok=True)
    marker = {
        "active_root": str(root),
        "version": "16.3.25.5.50-runtime-reload-daemon-lifecycle-hotfix",
        "daemon_pid": 4242,
        "daemon_instance_id": "old-instance",
        "last_heartbeat_at_utc": datetime.now(timezone.utc).isoformat(),
        "heartbeat_interval_seconds": 30.0,
        "process_fingerprint": {
            "schema_version": PROCESS_FINGERPRINT_SCHEMA_VERSION,
            "pid": 4242,
            "platform": os.name,
            "available": True,
            "identity_token": "old-process-token",
            "state": "observed",
        },
    }
    marker_path.write_text(json.dumps(marker), encoding="utf-8")

    monkeypatch.setattr(
        runtime_daemon,
        "resolve_active_runtime_root",
        lambda *_a, **_k: SimpleNamespace(
            root=root, marker_found=True, marker_valid=True, source="active_marker", error=None
        ),
    )
    monkeypatch.setattr(runtime_daemon, "verify_package_integrity_manifest", lambda _root: {"ok": True})
    monkeypatch.setattr(
        runtime_daemon,
        "read_source_provenance",
        lambda *_a, **_k: SimpleNamespace(
            to_dict=lambda: {"status": "verified_export_without_git_history"}
        ),
    )
    monkeypatch.setattr(runtime_daemon, "pid_is_alive", lambda _pid: True)
    monkeypatch.setattr(
        runtime_daemon,
        "process_fingerprint",
        lambda pid: {
            "schema_version": PROCESS_FINGERPRINT_SCHEMA_VERSION,
            "pid": pid,
            "platform": os.name,
            "available": True,
            "identity_token": "reused-pid-token",
            "state": "observed",
        },
    )
    monkeypatch.setattr(
        runtime_daemon,
        "_probe_daemon_status",
        lambda *_a, **_k: (None, "connection refused", None),
    )
    monkeypatch.setattr(
        runtime_daemon,
        "read_runtime_version_from_version_py",
        lambda *_a, **_k: "16.3.25.5.50-runtime-reload-daemon-lifecycle-hotfix",
    )

    status = runtime_daemon.status_daemon(JaznConfig(root=root), probe_endpoint=True)
    assert status["pid_alive_os_probe"] is True
    assert status["process_fingerprint_match"] is False
    assert status["pid_alive"] is False
    assert status["process_state"] == "pid_reused"
    assert status["identity_state"] == "process_fingerprint_mismatch"
    assert status["active_state"] == "inactive"
    assert status["active_state_reason"] == "pid_reused_process_fingerprint_mismatch"
