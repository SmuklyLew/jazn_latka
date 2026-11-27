"""F06: verified restore cannot copy or roll back memory before verified stop."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from latka_jazn.tools import verified_memory_restore as restore


def _inactive_supervisor(root: Path) -> dict[str, Any]:
    return {
        "_exit_code": 1, "root": str(root), "supervisor_active": False,
        "supervisor_pid_alive": False, "supervisor_identity_state": "not_alive",
        "supervisor_pid": None, "supervisor_owner_record_present": False,
    }


def _stopped(root: Path) -> dict[str, Any]:
    return {
        "_exit_code": 1, "root": str(root), "status_scope": "live_endpoint",
        "daemon": {
            "active_root": str(root), "active_state": "inactive",
            "stopped_confirmed": True, "pid_alive_os_probe": False,
            "endpoint_probe_performed": True, "endpoint_reachable": False,
        },
    }


@pytest.mark.parametrize("damage", [
    "live", "snapshot", "wrong_root", "no_stop_marker", "live_pid", "endpoint_unknown",
    "supervisor_alive", "supervisor_unknown", "supervisor_owner_without_pid",
])
def test_maintenance_observation_requires_canonical_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, damage: str,
) -> None:
    daemon = _stopped(tmp_path)
    supervisor = _inactive_supervisor(tmp_path)
    if damage == "live":
        daemon["daemon"]["active_state"] = "active_degraded"
    elif damage == "snapshot":
        daemon["status_scope"] = "offline_snapshot"
    elif damage == "wrong_root":
        daemon["daemon"]["active_root"] = str(tmp_path / "other")
    elif damage == "no_stop_marker":
        daemon["daemon"]["stopped_confirmed"] = False
    elif damage == "live_pid":
        daemon["daemon"]["pid_alive_os_probe"] = True
    elif damage == "endpoint_unknown":
        daemon["daemon"]["endpoint_reachable"] = None
    elif damage == "supervisor_alive":
        supervisor["supervisor_pid_alive"] = True
    elif damage == "supervisor_unknown":
        supervisor.pop("supervisor_identity_state")
    else:
        supervisor["supervisor_owner_record_present"] = True

    def observe(root: Path, arguments: list[str], **kwargs: Any) -> dict[str, Any]:
        assert root == tmp_path
        assert kwargs["allowed_exit_codes"] == (0, 1)
        assert arguments in (["status", "--json"], ["supervisor-status", "--json"])
        return supervisor if arguments[0] == "supervisor-status" else daemon

    monkeypatch.setattr(restore, "_run_json", observe)
    with pytest.raises(restore.VerifiedMemoryRestoreError):
        restore._require_quiescent_runtime(tmp_path)


def test_confirmed_inactive_status_accepts_nonzero_exit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def observe(_root: Path, arguments: list[str], **kwargs: Any) -> dict[str, Any]:
        assert kwargs["allowed_exit_codes"] == (0, 1)
        if arguments == ["supervisor-status", "--json"]:
            return _inactive_supervisor(tmp_path)
        assert arguments == ["status", "--json"]
        return _stopped(tmp_path)
    monkeypatch.setattr(restore, "_run_json", observe)
    result = restore._require_quiescent_runtime(tmp_path)
    assert result["daemon_status"]["daemon"]["stopped_confirmed"] is True


@pytest.mark.parametrize("failure", [
    "supervisor", "stop", "before_backup", "before_publish", "publication", "restart_before_rollback",
])
def test_prepare_never_rolls_back_without_authorized_publication_and_quiescence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str,
) -> None:
    events: list[str] = []
    (tmp_path / "run.py").write_text("# synthetic, never executed", encoding="utf-8")
    monkeypatch.setattr(restore, "validate_test04_summary", lambda _p: {})
    monkeypatch.setattr(restore, "validate_test04_databases", lambda _p: {})
    monkeypatch.setattr(restore.RuntimeArchiveConverter, "build", lambda _self: {})

    def supervisor(_root: Path) -> dict[str, Any]:
        events.append("supervisor")
        if failure == "supervisor":
            raise restore.VerifiedMemoryRestoreError("synthetic supervisor running")
        return _inactive_supervisor(tmp_path)

    def stop(_root: Path) -> dict[str, Any]:
        events.append("stop")
        if failure == "stop":
            raise restore.VerifiedMemoryRestoreError("synthetic stop failed")
        return {"exit_code": 0}

    def quiescent(_root: Path) -> dict[str, Any]:
        events.append("observe")
        index = events.count("observe")
        if (failure, index) in {
            ("before_backup", 1), ("before_publish", 2), ("restart_before_rollback", 3),
        }:
            raise restore.VerifiedMemoryRestoreError("synthetic stop not verified")
        return {"daemon_status": _stopped(tmp_path)}

    def backup(_root: Path, backup_root: Path) -> dict[str, Any]:
        events.append("backup")
        backup_root.mkdir()
        (backup_root / "canary").write_text("preserved", encoding="utf-8")
        return {"ok": True}

    def publish(_staged: Path, _root: Path) -> dict[str, Any]:
        events.append("publish")
        raise restore.VerifiedMemoryRestoreError("synthetic publication failure")

    def rollback(_root: Path, backup_root: Path) -> None:
        events.append("rollback")
        assert (backup_root / "canary").read_text(encoding="utf-8") == "preserved"

    monkeypatch.setattr(restore, "_require_inactive_supervisor", supervisor)
    monkeypatch.setattr(restore, "_stop_daemon", stop)
    monkeypatch.setattr(restore, "_require_quiescent_runtime", quiescent)
    monkeypatch.setattr(restore, "_backup_runtime_memory", backup)
    monkeypatch.setattr(restore, "_publish_staged_archive", publish)
    monkeypatch.setattr(restore, "_restore_runtime_memory", rollback)
    with pytest.raises(restore.VerifiedMemoryRestoreError) as caught:
        restore.prepare(
            tmp_path, test04_root=tmp_path / "source", test04_summary=tmp_path / "summary.json",
            publish=True, stop_daemon=True, l2_limit=1, report_path=None,
        )
    expected = {
        "supervisor": ["supervisor"],
        "stop": ["supervisor", "stop"],
        "before_backup": ["supervisor", "stop", "observe"],
        "before_publish": ["supervisor", "stop", "observe", "backup", "observe"],
        "publication": ["supervisor", "stop", "observe", "backup", "observe", "publish", "observe", "rollback"],
        "restart_before_rollback": ["supervisor", "stop", "observe", "backup", "observe", "publish", "observe"],
    }
    assert events == expected[failure]
    if failure == "restart_before_rollback":
        assert "Rollback zablokowany" in str(caught.value)
        assert list(tmp_path.rglob("backup_before_publish/canary"))


def test_staging_only_never_touches_live_memory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "run.py").write_text("# synthetic", encoding="utf-8")
    monkeypatch.setattr(restore, "validate_test04_summary", lambda _p: {})
    monkeypatch.setattr(restore, "validate_test04_databases", lambda _p: {})
    monkeypatch.setattr(restore.RuntimeArchiveConverter, "build", lambda _self: {})
    def forbidden(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("stage-only must not touch the runtime")
    for name in ("_require_inactive_supervisor", "_require_quiescent_runtime", "_stop_daemon",
                 "_backup_runtime_memory", "_publish_staged_archive", "_restore_runtime_memory"):
        monkeypatch.setattr(restore, name, forbidden)
    result = restore.prepare(
        tmp_path, test04_root=tmp_path / "source", test04_summary=tmp_path / "summary.json",
        publish=False, stop_daemon=False, l2_limit=1, report_path=None,
    )
    assert result.status == "staged"
