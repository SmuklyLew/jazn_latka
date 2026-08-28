from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from latka_jazn.config import JaznConfig
from latka_jazn.core import daemon_autostart, runtime_daemon
from latka_jazn.core.runtime_root import active_runtime_marker_path


def _runtime_root(path: Path) -> Path:
    root = path.resolve()
    package = root / "latka_jazn"
    package.mkdir(parents=True)
    (package / "version.py").write_text('PACKAGE_VERSION = "test"\n', encoding="utf-8")
    (root / "run.py").write_text("", encoding="utf-8")
    return root


def _write_subject_marker(requested_root: Path, subject_root: Path) -> Path:
    marker_path = active_runtime_marker_path(requested_root)
    marker_path.parent.mkdir(parents=True)
    marker_path.write_text(
        json.dumps(
            {
                "active_root": str(subject_root.resolve()),
                "pid": 4321,
                "last_heartbeat_at_utc": "2026-08-28T12:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )
    return marker_path


def _status(
    requested_root: Path,
    subject_root: Path,
    *,
    state: str,
    identity_matches: bool,
) -> dict[str, Any]:
    return {
        "active_state": state,
        "active_state_reason": (
            "endpoint_runtime_identity_confirmed"
            if identity_matches
            else "daemon_not_running"
        ),
        "requested_runtime_root": str(requested_root),
        "resolved_active_root": str(subject_root),
        "subject_runtime_root": str(subject_root),
        "endpoint_reported_active_root": str(subject_root) if identity_matches else None,
        "endpoint_identity_matches": identity_matches,
        "endpoint_reachable": identity_matches,
        "pid": 4321 if identity_matches else None,
        "pid_alive": identity_matches,
    }


def test_ensure_starts_resolved_subject_b_never_requested_a(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requested_root = _runtime_root(tmp_path / "runtime_A")
    subject_root = _runtime_root(tmp_path / "runtime_B")
    statuses = [
        _status(requested_root, subject_root, state="inactive", identity_matches=False),
        _status(requested_root, subject_root, state="active_trusted", identity_matches=True),
    ]
    start_roots: list[Path] = []
    monkeypatch.setattr(
        daemon_autostart,
        "status_daemon",
        lambda *_args, **_kwargs: statuses.pop(0),
    )

    def record_start(config: JaznConfig, **_kwargs: Any) -> dict[str, Any]:
        start_roots.append(Path(config.root).resolve())
        return {"ok": True, "started": True}

    monkeypatch.setattr(daemon_autostart, "start_daemon", record_start)

    result = daemon_autostart.ensure_daemon_for_runtime_turn(
        JaznConfig(root=requested_root),
        command="--chat",
        env={},
    )

    assert result.ok is True
    assert start_roots == [subject_root]
    assert requested_root not in start_roots


def test_start_daemon_integrity_gate_targets_resolved_subject_b(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requested_root = _runtime_root(tmp_path / "runtime_A")
    subject_root = _runtime_root(tmp_path / "runtime_B")
    _write_subject_marker(requested_root, subject_root)
    integrity_roots: list[Path] = []

    def reject_after_recording(root: Path) -> dict[str, Any]:
        integrity_roots.append(Path(root).resolve())
        return {"ok": False, "errors": [{"code": "synthetic_stop_after_subject_assertion"}]}

    monkeypatch.setattr(runtime_daemon, "verify_package_integrity_manifest", reject_after_recording)

    result = runtime_daemon.start_daemon(JaznConfig(root=requested_root), startup_timeout=0.01)

    assert result["ok"] is False
    assert result["error_code"] == "package_integrity_verification_failed"
    assert integrity_roots == [subject_root]
    assert result["requested_runtime_root"] == str(requested_root)
    assert result["resolved_active_root"] == str(subject_root)


def test_stop_uses_subject_b_capability_token_after_identity_confirmation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requested_root = _runtime_root(tmp_path / "runtime_A")
    subject_root = _runtime_root(tmp_path / "runtime_B")
    statuses = [
        _status(requested_root, subject_root, state="active_trusted", identity_matches=True),
        _status(requested_root, subject_root, state="inactive", identity_matches=False),
    ]
    token_roots: list[Path] = []
    http_tokens: list[str | None] = []
    monkeypatch.setattr(
        runtime_daemon,
        "status_daemon",
        lambda *_args, **_kwargs: statuses.pop(0),
    )

    def read_token(root: Path) -> str:
        token_roots.append(Path(root).resolve())
        return "subject-b-token"

    def fake_http(
        method: str,
        _url: str,
        _payload: dict[str, Any] | None = None,
        *,
        timeout: float,
        token: str | None = None,
    ) -> dict[str, Any]:
        assert method == "POST"
        assert timeout == 2.0
        http_tokens.append(token)
        return {"ok": True}

    monkeypatch.setattr(runtime_daemon, "read_daemon_auth_token", read_token)
    monkeypatch.setattr(runtime_daemon, "http_json", fake_http)

    result = runtime_daemon.stop_daemon(
        JaznConfig(root=requested_root),
        timeout=0.0,
    )

    assert result["ok"] is True
    assert token_roots == [subject_root]
    assert http_tokens == ["subject-b-token"]


@pytest.mark.parametrize(
    ("operation", "response_key"),
    [
        ("refresh", "refresh_response"),
        ("inject", "inject_response"),
        ("init", "init_response"),
    ],
)
def test_control_operations_use_subject_b_capability_token(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
    response_key: str,
) -> None:
    requested_root = _runtime_root(tmp_path / "runtime_A")
    subject_root = _runtime_root(tmp_path / "runtime_B")
    healthy = _status(
        requested_root,
        subject_root,
        state="active_trusted",
        identity_matches=True,
    )
    token_roots: list[Path] = []
    http_tokens: list[str | None] = []
    monkeypatch.setattr(runtime_daemon, "status_daemon", lambda *_args, **_kwargs: healthy)
    monkeypatch.setattr(
        runtime_daemon,
        "read_daemon_auth_token",
        lambda root: token_roots.append(Path(root).resolve()) or "subject-b-token",
    )
    monkeypatch.setattr(
        runtime_daemon,
        "_probe_daemon_status",
        lambda *_args, **_kwargs: (
            {**healthy, "timestamp_trusted": True},
            None,
            "/live",
        ),
    )

    def fake_http(
        _method: str,
        _url: str,
        _payload: dict[str, Any] | None = None,
        *,
        timeout: float,
        token: str | None = None,
    ) -> dict[str, Any]:
        del timeout
        http_tokens.append(token)
        return {"ok": True, "active_state": "active_trusted", "timestamp_trusted": True}

    monkeypatch.setattr(runtime_daemon, "http_json", fake_http)
    config = JaznConfig(root=requested_root)
    if operation == "refresh":
        result = runtime_daemon.refresh_daemon_time(config)
    elif operation == "inject":
        result = runtime_daemon.inject_daemon_trusted_time(
            config,
            trusted_time_iso="2026-08-28T12:00:00+00:00",
        )
    else:
        result = runtime_daemon.init_runtime_write_v1_daemon(config)

    assert result[response_key] is not None
    assert token_roots == [subject_root]
    assert http_tokens == ["subject-b-token"]


def test_control_operation_refuses_identity_mismatch_before_http_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requested_root = _runtime_root(tmp_path / "runtime_A")
    subject_root = _runtime_root(tmp_path / "runtime_B")
    mismatched = _status(
        requested_root,
        subject_root,
        state="inactive",
        identity_matches=False,
    )
    monkeypatch.setattr(runtime_daemon, "status_daemon", lambda *_args, **_kwargs: mismatched)
    monkeypatch.setattr(
        runtime_daemon,
        "http_json",
        lambda *_args, **_kwargs: pytest.fail("identity mismatch must block the control request"),
    )

    result = runtime_daemon.init_runtime_write_v1_daemon(JaznConfig(root=requested_root))

    assert result["ok"] is False
    assert result["error_code"] == "daemon_identity_not_confirmed"
    assert result["init_response"] is None
