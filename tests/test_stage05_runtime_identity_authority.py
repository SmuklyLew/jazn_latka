"""Stage 05 runtime identity authority: no conversational daemon bypass."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

import main as main_module
from latka_jazn.config import JaznConfig
from latka_jazn.core import daemon_autostart
from latka_jazn.core.daemon_autostart import DaemonEnsureResult


@pytest.mark.parametrize("command", ["--chat", "--chat-gpt", "--chat-gpt-final-only", "--chat-ollama", "--chat-open-ai", "direct_message"])
def test_disabled_autostart_never_authorizes_conversation_without_daemon(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, command: str,
) -> None:
    monkeypatch.setattr(daemon_autostart, "status_daemon", lambda *a, **k: {
        "active_state": "inactive", "active_state_reason": "daemon_not_running",
    })
    monkeypatch.setattr(daemon_autostart, "start_daemon", lambda *a, **k: pytest.fail("disabled startup"))
    result = daemon_autostart.ensure_daemon_for_runtime_turn(
        JaznConfig(root=tmp_path), command=command, disabled_for_turn=True, env={},
    )
    assert not result.ok
    assert result.selected_transport == "host_diagnostic"
    assert not result.one_shot_allowed
    assert not result.one_shot_verified


@pytest.mark.parametrize("explicit", [False, True])
def test_chatgpt_transport_loss_never_replays_as_local_bridge(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str], explicit: bool,
) -> None:
    ensure = DaemonEnsureResult(
        ok=True, ensured=True, active_state="active_trusted",
        reason="daemon_already_active", decision={"explicit_ensure": explicit},
        selected_transport="persistent_daemon", daemon_identity_verified=True,
    )
    monkeypatch.setattr(main_module, "_ensure_daemon_for_cli_turn", lambda *a, **k: ensure)
    attempts: list[dict[str, Any]] = []

    def lost(**kwargs: Any) -> None:
        attempts.append(kwargs)
        return None

    monkeypatch.setattr(main_module, "_try_chat_gpt_one_shot_via_daemon", lost)
    monkeypatch.setattr(main_module, "run_jsonl_chat_bridge", lambda **k: pytest.fail("local replay forbidden"))
    assert main_module.main([
        "--root", str(tmp_path), "--no-runtime-preflight",
        "--chat-gpt", "--daemon-request-id", "identity-test-request", "--", "Hej.",
    ]) == 1
    assert len(attempts) == 1
    assert attempts[0]["request_id"] == "identity-test-request"
    payload = json.loads(capsys.readouterr().out)
    assert payload["action"] == "host_diagnostic"
    assert payload["request_id"] == "identity-test-request"
    assert payload["request_acceptance"] == "unknown"
    assert payload["must_not_claim_runtime_voice"] is True
    assert payload["must_not_replay"] is True
    assert payload["transport_observability"]["selected_transport"] == "host_diagnostic"
    assert payload["transport_observability"]["one_shot_allowed"] is False
