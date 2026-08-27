from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from latka_jazn.config import JaznConfig
from latka_jazn.core import runtime_daemon
from latka_jazn.core.runtime_root import active_runtime_marker_path


def _runtime_root(path: Path) -> Path:
    root = path.resolve()
    package = root / "latka_jazn"
    package.mkdir(parents=True)
    (package / "version.py").write_text('PACKAGE_VERSION = "test"\n', encoding="utf-8")
    (root / "run.py").write_text("", encoding="utf-8")
    return root


def _heartbeat() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stale_heartbeat() -> str:
    return (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()


def _marker(root: Path, *, pid: int = 4321) -> dict[str, object]:
    return {
        "pid": pid,
        "active_root": str(root.resolve()),
        "last_heartbeat_at_utc": _heartbeat(),
        "heartbeat_interval_seconds": 10,
        "timestamp_contract": {"trusted": False, "source": "local_machine"},
    }


def _ping(root: Path, *, pid: int = 4321, heartbeat: str | None = None) -> dict[str, object]:
    return {
        "daemon_pid": pid,
        "runtime_process_active": True,
        "active_root": str(root.resolve()),
        "last_heartbeat_at_utc": heartbeat or _heartbeat(),
        "heartbeat_interval_seconds": 10,
        "timestamp_trusted": False,
        "timestamp_contract": {"trusted": False, "source": "local_machine"},
    }


def _install_subject_runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    endpoint_root: Path | None = None,
    endpoint_pid: int = 4321,
    heartbeat: str | None = None,
) -> tuple[Path, Path, list[Path], list[Path]]:
    requested_root = _runtime_root(tmp_path / "runtime_A")
    subject_root = _runtime_root(tmp_path / "runtime_B")
    marker_path = active_runtime_marker_path(requested_root)
    marker_path.parent.mkdir(parents=True)
    marker_path.write_text(json.dumps(_marker(subject_root)), encoding="utf-8")

    integrity_calls: list[Path] = []
    provenance_calls: list[Path] = []

    def verify(root: Path) -> dict[str, object]:
        integrity_calls.append(Path(root).resolve())
        return {"ok": True, "errors": []}

    def provenance(root: Path, **_kwargs: object) -> SimpleNamespace:
        provenance_calls.append(Path(root).resolve())
        return SimpleNamespace(
            to_dict=lambda: {
                "status": "verified_export_without_git_history",
                "limitations": ["synthetic subject-root contract fixture"],
            }
        )

    ping = _ping(endpoint_root or subject_root, pid=endpoint_pid, heartbeat=heartbeat)
    monkeypatch.setattr(runtime_daemon, "verify_package_integrity_manifest", verify)
    monkeypatch.setattr(runtime_daemon, "read_source_provenance", provenance)
    monkeypatch.setattr(runtime_daemon, "pid_is_alive", lambda _pid: True)
    monkeypatch.setattr(
        runtime_daemon,
        "_probe_daemon_status",
        lambda *_args, **_kwargs: (ping, None, "/ready"),
    )
    return requested_root, subject_root, integrity_calls, provenance_calls


def test_status_trusts_resolved_subject_runtime_for_sibling_root_a_b_b(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requested_root, subject_root, integrity_calls, provenance_calls = _install_subject_runtime(
        tmp_path,
        monkeypatch,
    )

    result = runtime_daemon.status_daemon(JaznConfig(root=requested_root))

    assert result["active_state"] == "active_trusted"
    assert result["active_root"] == str(subject_root)
    assert result["requested_runtime_root"] == str(requested_root)
    assert result["resolved_active_root"] == str(subject_root)
    assert result["subject_runtime_root"] == str(subject_root)
    assert result["endpoint_expected_active_root"] == str(subject_root)
    assert result["endpoint_reported_active_root"] == str(subject_root)
    assert result["endpoint_root_matches"] is True
    assert result["endpoint_pid_matches"] is True
    assert result["endpoint_identity_matches"] is True
    assert result["package_integrity_verified"] is True
    assert result["source_provenance_verified"] is True
    assert integrity_calls == [subject_root]
    assert provenance_calls == [subject_root]


def test_sibling_root_endpoint_c_stays_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    endpoint_root = (tmp_path / "runtime_C").resolve()
    requested_root, subject_root, integrity_calls, provenance_calls = _install_subject_runtime(
        tmp_path,
        monkeypatch,
        endpoint_root=endpoint_root,
    )

    result = runtime_daemon.status_daemon(JaznConfig(root=requested_root))

    assert result["active_state"] == "inactive"
    assert result["active_state_reason"] == "endpoint_runtime_root_mismatch"
    assert result["endpoint_root_matches"] is False
    assert integrity_calls == [subject_root]
    assert provenance_calls == [subject_root]


def test_sibling_root_wrong_pid_stays_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requested_root, subject_root, _, _ = _install_subject_runtime(
        tmp_path,
        monkeypatch,
        endpoint_pid=9876,
    )

    result = runtime_daemon.status_daemon(JaznConfig(root=requested_root))

    assert result["active_root"] == str(subject_root)
    assert result["active_state"] == "inactive"
    assert result["active_state_reason"] == "endpoint_pid_mismatch"
    assert result["endpoint_pid_matches"] is False


def test_sibling_root_stale_heartbeat_is_degraded_not_trusted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requested_root, subject_root, _, _ = _install_subject_runtime(
        tmp_path,
        monkeypatch,
        heartbeat=_stale_heartbeat(),
    )

    result = runtime_daemon.status_daemon(JaznConfig(root=requested_root))

    assert result["active_root"] == str(subject_root)
    assert result["active_state"] == "active_degraded"
    assert result["active_state_reason"] == "endpoint_identity_confirmed_heartbeat_stale"
    assert result["heartbeat_fresh"] is False


def test_integrity_failure_is_evaluated_for_subject_b_and_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requested_root, subject_root, integrity_calls, _ = _install_subject_runtime(
        tmp_path,
        monkeypatch,
    )

    def failed_integrity(root: Path) -> dict[str, object]:
        integrity_calls.append(Path(root).resolve())
        return {"ok": False, "errors": [{"code": "sha256_mismatch", "path": "run.py"}]}

    integrity_calls.clear()
    monkeypatch.setattr(runtime_daemon, "verify_package_integrity_manifest", failed_integrity)
    result = runtime_daemon.status_daemon(JaznConfig(root=requested_root))

    assert result["active_state"] == "inactive"
    assert result["active_state_reason"] == "package_integrity_verification_failed"
    assert integrity_calls == [subject_root]


def test_invalid_provenance_is_evaluated_for_subject_b_and_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requested_root, subject_root, _, provenance_calls = _install_subject_runtime(
        tmp_path,
        monkeypatch,
    )

    def invalid_provenance(root: Path, **_kwargs: object) -> SimpleNamespace:
        provenance_calls.append(Path(root).resolve())
        return SimpleNamespace(to_dict=lambda: {"status": "invalid", "limitations": ["test"]})

    provenance_calls.clear()
    monkeypatch.setattr(runtime_daemon, "read_source_provenance", invalid_provenance)
    result = runtime_daemon.status_daemon(JaznConfig(root=requested_root))

    assert result["active_state"] == "inactive"
    assert result["active_state_reason"] == "source_provenance_not_verified"
    assert provenance_calls == [subject_root]


def test_broken_requested_a_does_not_reject_verified_subject_b(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requested_root, subject_root, integrity_calls, provenance_calls = _install_subject_runtime(
        tmp_path,
        monkeypatch,
    )
    (requested_root / "latka_jazn" / "version.py").unlink()

    result = runtime_daemon.status_daemon(JaznConfig(root=requested_root))

    assert result["active_state"] == "active_trusted"
    assert integrity_calls == [subject_root]
    assert provenance_calls == [subject_root]


@pytest.mark.parametrize(
    ("marker_text", "reason_prefix"),
    [
        ("{invalid-json", "active_marker_invalid_json"),
        (json.dumps({"pid": 4321, "active_root": ""}), "marker_active_root_empty"),
        (json.dumps({"pid": 4321, "active_root": "relative/runtime"}), "marker_active_root_not_absolute"),
    ],
)
def test_invalid_marker_stays_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    marker_text: str,
    reason_prefix: str,
) -> None:
    requested_root, _, _, _ = _install_subject_runtime(tmp_path, monkeypatch)
    active_runtime_marker_path(requested_root).write_text(marker_text, encoding="utf-8")

    result = runtime_daemon.status_daemon(JaznConfig(root=requested_root))

    assert result["active_state"] == "inactive"
    assert result["marker_valid"] is False
    assert result["active_state_reason"].startswith(reason_prefix)
