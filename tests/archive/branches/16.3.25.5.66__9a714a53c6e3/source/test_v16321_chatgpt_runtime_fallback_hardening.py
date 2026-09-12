from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

import main as main_module
from latka_jazn.config import JaznConfig
from latka_jazn.core import daemon_autostart


def _inactive_status() -> dict[str, Any]:
    return {
        "active_state": "inactive",
        "active_state_reason": "daemon_not_running",
        "endpoint_reachable": False,
    }


def test_chatgpt_default_policy_allows_verified_one_shot_fallback() -> None:
    decision = daemon_autostart.daemon_autostart_decision("--chat-gpt", env={})

    assert decision.command_known_runtime_turn is True
    assert decision.should_ensure is False
    assert decision.reason == "verified_one_shot_fallback_allowed"


def test_generic_chat_still_requires_daemon_by_default() -> None:
    decision = daemon_autostart.daemon_autostart_decision("--chat", env={})

    assert decision.command_known_runtime_turn is True
    assert decision.should_ensure is True
    assert decision.reason == "runtime_turn_requires_daemon"


def test_explicit_chatgpt_daemon_requirement_remains_fail_closed() -> None:
    cli = daemon_autostart.daemon_autostart_decision(
        "--chat-gpt",
        explicit_ensure=True,
        env={},
    )
    env = daemon_autostart.daemon_autostart_decision(
        "--chat-gpt",
        env={daemon_autostart.FORCE_ENSURE_ENV: "1"},
    )

    assert cli.should_ensure is True
    assert cli.reason == "explicit_ensure_daemon"
    assert env.should_ensure is True
    assert env.reason == "env_JAZN_ENSURE_DAEMON"


def test_default_chatgpt_ensure_does_not_spawn_daemon_when_inactive(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    starts: list[bool] = []
    monkeypatch.setattr(
        daemon_autostart,
        "status_daemon",
        lambda *_args, **_kwargs: _inactive_status(),
    )

    def unexpected_start(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        starts.append(True)
        raise AssertionError("default --chat-gpt must not require daemon autostart")

    monkeypatch.setattr(daemon_autostart, "start_daemon", unexpected_start)

    result = daemon_autostart.ensure_daemon_for_runtime_turn(
        JaznConfig(root=tmp_path),
        command="--chat-gpt",
        env={},
    )

    assert starts == []
    assert result.ok is False
    assert result.ensured is False
    assert result.reason == "verified_one_shot_fallback_allowed"
    assert result.decision["should_ensure"] is False


def test_explicit_chatgpt_ensure_still_attempts_daemon_and_reports_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    starts: list[bool] = []
    monkeypatch.setattr(
        daemon_autostart,
        "status_daemon",
        lambda *_args, **_kwargs: _inactive_status(),
    )

    def failed_start(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        starts.append(True)
        return {"ok": False, "active_state": "inactive"}

    monkeypatch.setattr(daemon_autostart, "start_daemon", failed_start)

    result = daemon_autostart.ensure_daemon_for_runtime_turn(
        JaznConfig(root=tmp_path),
        command="--chat-gpt",
        explicit_ensure=True,
        env={},
    )

    assert starts == [True]
    assert result.ok is False
    assert result.reason == "daemon_start_failed"
    assert result.decision["should_ensure"] is True
    assert result.decision["explicit_ensure"] is True


def test_chatgpt_main_reaches_local_bridge_when_daemon_is_unavailable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        daemon_autostart,
        "status_daemon",
        lambda *_args, **_kwargs: _inactive_status(),
    )
    monkeypatch.setattr(
        daemon_autostart,
        "start_daemon",
        lambda *_args, **_kwargs: pytest.fail("default --chat-gpt attempted daemon start"),
    )
    monkeypatch.setattr(
        main_module,
        "_try_chat_gpt_one_shot_via_daemon",
        lambda **_kwargs: None,
    )
    calls: list[dict[str, Any]] = []

    def fake_local_bridge(**kwargs: Any) -> int:
        calls.append(kwargs)
        return 0

    monkeypatch.setattr(main_module, "run_jsonl_chat_bridge", fake_local_bridge)

    exit_code = main_module.main(
        [
            "--root",
            str(tmp_path),
            "--no-runtime-preflight",
            "--chat-gpt",
            "--",
            "Hej Łatko",
        ]
    )

    assert exit_code == 0
    assert len(calls) == 1
    assert calls[0]["command"] == "--chat-gpt"
    assert calls[0]["require_openai_api_key"] is False
    assert calls[0]["output_mode"] == "host_packet"
    assert calls[0]["one_shot_degraded"] is True
