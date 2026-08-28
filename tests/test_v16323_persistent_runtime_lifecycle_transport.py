from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

import main as main_module
from latka_jazn.config import JaznConfig
from latka_jazn.core import chat_command_contract, daemon_autostart, runtime_daemon
from latka_jazn.core.daemon_autostart import DaemonEnsureResult
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
    assert result.selected_transport == "persistent_daemon"
    assert result.fallback_reason == "daemon_started"
    assert result.requested_runtime_root == str(requested_root)
    assert result.resolved_active_root == str(subject_root)
    assert result.daemon_endpoint_root == str(subject_root)
    assert result.daemon_identity_verified is True
    assert result.daemon_reused is False
    assert result.daemon_started is True
    assert result.one_shot_allowed is False


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


def test_healthy_subject_b_reports_persistent_daemon_reuse(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requested_root = _runtime_root(tmp_path / "runtime_A")
    subject_root = _runtime_root(tmp_path / "runtime_B")
    healthy = _status(
        requested_root,
        subject_root,
        state="active_trusted",
        identity_matches=True,
    )
    monkeypatch.setattr(daemon_autostart, "status_daemon", lambda *_args, **_kwargs: healthy)
    monkeypatch.setattr(
        daemon_autostart,
        "start_daemon",
        lambda *_args, **_kwargs: pytest.fail("healthy subject B must be reused"),
    )

    result = daemon_autostart.ensure_daemon_for_runtime_turn(
        JaznConfig(root=requested_root),
        command="--chat-gpt",
        env={},
    )
    transport = result.transport_observability()

    assert result.ok is True
    assert transport == {
        "selected_transport": "persistent_daemon",
        "fallback_reason": "daemon_reused",
        "requested_runtime_root": str(requested_root),
        "resolved_active_root": str(subject_root),
        "daemon_endpoint_root": str(subject_root),
        "daemon_identity_verified": True,
        "daemon_reused": True,
        "daemon_started": False,
        "one_shot_allowed": False,
        "one_shot_verified": False,
    }


def test_inactive_chatgpt_reports_controlled_one_shot_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _runtime_root(tmp_path / "runtime_A")
    inactive = _status(root, root, state="inactive", identity_matches=False)
    monkeypatch.setattr(daemon_autostart, "status_daemon", lambda *_args, **_kwargs: inactive)

    result = daemon_autostart.ensure_daemon_for_runtime_turn(
        JaznConfig(root=root),
        command="--chat-gpt",
        env={},
    )

    assert result.selected_transport == "verified_one_shot_fallback"
    assert result.fallback_reason == "verified_one_shot_fallback_allowed"
    assert result.one_shot_allowed is True
    assert result.one_shot_verified is False


@pytest.mark.parametrize(
    ("active_reason", "fallback_reason"),
    [
        ("endpoint_runtime_root_mismatch", "daemon_identity_root_mismatch"),
        ("endpoint_pid_mismatch", "daemon_identity_pid_mismatch"),
        ("endpoint_identity_confirmed_heartbeat_stale", "daemon_heartbeat_stale"),
        ("package_integrity_verification_failed", "runtime_integrity_failure"),
        ("source_provenance_not_verified", "runtime_provenance_failure"),
    ],
)
def test_truth_boundary_failure_never_downgrades_to_one_shot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    active_reason: str,
    fallback_reason: str,
) -> None:
    requested_root = _runtime_root(tmp_path / "runtime_A")
    subject_root = _runtime_root(tmp_path / "runtime_B")
    failed = _status(
        requested_root,
        subject_root,
        state="inactive",
        identity_matches=False,
    )
    failed["active_state_reason"] = active_reason
    monkeypatch.setattr(daemon_autostart, "status_daemon", lambda *_args, **_kwargs: failed)

    result = daemon_autostart.ensure_daemon_for_runtime_turn(
        JaznConfig(root=requested_root),
        command="--chat-gpt",
        env={},
    )

    assert result.selected_transport == "host_diagnostic"
    assert result.fallback_reason == fallback_reason
    assert result.one_shot_allowed is False


def test_explicit_ensure_failure_reports_no_one_shot_transport(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _runtime_root(tmp_path / "runtime_A")
    inactive = _status(root, root, state="inactive", identity_matches=False)
    monkeypatch.setattr(daemon_autostart, "status_daemon", lambda *_args, **_kwargs: inactive)
    monkeypatch.setattr(
        daemon_autostart,
        "start_daemon",
        lambda *_args, **_kwargs: {"ok": False, "started": False},
    )

    result = daemon_autostart.ensure_daemon_for_runtime_turn(
        JaznConfig(root=root),
        command="--chat-gpt",
        explicit_ensure=True,
        env={},
    )

    assert result.ok is False
    assert result.selected_transport == "host_diagnostic"
    assert result.fallback_reason == "daemon_start_required_failed"
    assert result.one_shot_allowed is False


def test_invalid_active_marker_is_ambiguous_and_never_allows_one_shot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requested_root = _runtime_root(tmp_path / "runtime_A")
    subject_root = _runtime_root(tmp_path / "runtime_B")
    invalid = _status(
        requested_root,
        subject_root,
        state="inactive",
        identity_matches=False,
    )
    invalid.update(
        {
            "active_state_reason": "active_marker_invalid",
            "marker_found": True,
            "marker_valid": False,
        }
    )
    monkeypatch.setattr(daemon_autostart, "status_daemon", lambda *_args, **_kwargs: invalid)
    monkeypatch.setattr(
        daemon_autostart,
        "start_daemon",
        lambda *_args, **_kwargs: pytest.fail("ambiguous marker must block daemon start"),
    )

    result = daemon_autostart.ensure_daemon_for_runtime_turn(
        JaznConfig(root=requested_root),
        command="--chat-gpt",
        env={},
    )

    assert result.ok is False
    assert result.selected_transport == "host_diagnostic"
    assert result.fallback_reason == "ambiguous_subject_root"
    assert result.requested_runtime_root == str(requested_root)
    assert result.resolved_active_root == str(subject_root)
    assert result.daemon_identity_verified is False
    assert result.one_shot_allowed is False
    assert result.one_shot_verified is False


@pytest.mark.parametrize("persistent_reason", ["daemon_reused", "daemon_started"])
def test_verified_jsonl_one_shot_never_preserves_a_persistent_fallback_reason(
    persistent_reason: str,
) -> None:
    transport = {
        "selected_transport": "persistent_daemon",
        "fallback_reason": persistent_reason,
    }

    chat_command_contract._mark_verified_one_shot_transport(transport)

    assert transport == {
        "selected_transport": "verified_one_shot_fallback",
        "fallback_reason": "jsonl_bridge_uses_verified_one_shot",
        "one_shot_allowed": True,
        "one_shot_verified": True,
    }


def test_chatgpt_main_binds_persistent_turn_to_resolved_subject_b(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requested_root = _runtime_root(tmp_path / "runtime_A")
    subject_root = _runtime_root(tmp_path / "runtime_B")
    ensure = DaemonEnsureResult(
        ok=True,
        ensured=True,
        active_state="active_trusted",
        reason="already_active",
        decision={"should_ensure": False},
        selected_transport="persistent_daemon",
        fallback_reason="daemon_reused",
        requested_runtime_root=str(requested_root),
        resolved_active_root=str(subject_root),
        daemon_endpoint_root=str(subject_root),
        daemon_identity_verified=True,
        daemon_reused=True,
    )
    monkeypatch.setattr(
        main_module,
        "_ensure_daemon_for_cli_turn",
        lambda *_args, **_kwargs: ensure,
    )
    delegated: list[dict[str, Any]] = []

    def fake_daemon_turn(**kwargs: Any) -> int:
        delegated.append(kwargs)
        return 0

    monkeypatch.setattr(main_module, "_try_chat_gpt_one_shot_via_daemon", fake_daemon_turn)
    monkeypatch.setattr(
        main_module,
        "run_jsonl_chat_bridge",
        lambda **_kwargs: pytest.fail("healthy persistent B must not run one-shot"),
    )

    exit_code = main_module.main(
        [
            "--root",
            str(requested_root),
            "--no-runtime-preflight",
            "--chat-gpt",
            "--",
            "Zgadnij.",
        ]
    )

    assert exit_code == 0
    assert len(delegated) == 1
    assert delegated[0]["cfg"].root == subject_root
    assert delegated[0]["text"] == "Zgadnij."
    assert delegated[0]["transport_observability"]["requested_runtime_root"] == str(requested_root)
    assert delegated[0]["transport_observability"]["resolved_active_root"] == str(subject_root)
    assert delegated[0]["transport_observability"]["selected_transport"] == "persistent_daemon"


def test_chatgpt_main_explicit_ensure_failure_never_calls_one_shot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = _runtime_root(tmp_path / "runtime_A")
    inactive = _status(root, root, state="inactive", identity_matches=False)
    monkeypatch.setattr(daemon_autostart, "status_daemon", lambda *_args, **_kwargs: inactive)
    monkeypatch.setattr(
        daemon_autostart,
        "start_daemon",
        lambda *_args, **_kwargs: {"ok": False, "started": False},
    )
    monkeypatch.setattr(
        main_module,
        "_try_chat_gpt_one_shot_via_daemon",
        lambda **_kwargs: pytest.fail("failed explicit ensure must stop before a daemon turn"),
    )
    monkeypatch.setattr(
        main_module,
        "run_jsonl_chat_bridge",
        lambda **_kwargs: pytest.fail("failed explicit ensure must not run one-shot"),
    )

    exit_code = main_module.main(
        [
            "--root",
            str(root),
            "--no-runtime-preflight",
            "--ensure-daemon",
            "--chat-gpt",
            "--",
            "Hej.",
        ]
    )
    output = capsys.readouterr().out

    assert exit_code == 1
    assert '"error_code": "daemon_ensure_failed"' in output
    assert '"selected_transport": "host_diagnostic"' in output
    assert '"fallback_reason": "daemon_start_required_failed"' in output
