from __future__ import annotations

from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from latka_jazn.config import JaznConfig
from latka_jazn.core.conversation_channel import (
    canonical_chat_command,
    model_channel_public_metadata,
    normalize_model_channel_config,
    resolve_canonical_chat_session_id,
)
from latka_jazn.core.daemon_conversation_session import DaemonConversationSession
from latka_jazn.core import daemon_conversation_session as daemon_session_module
from latka_jazn.core import runtime_daemon
from latka_jazn.core.runtime_chat import LatkaRuntimeShell


def test_all_chat_adapters_share_one_default_session_identity() -> None:
    env: dict[str, str] = {}
    assert resolve_canonical_chat_session_id(None, env=env) == "jazn-main"
    assert canonical_chat_command("--chat") == "--chat"
    assert canonical_chat_command("--chat-gpt") == "--chat-gpt"
    assert canonical_chat_command("--chat-gpt-final-only") == "--chat-gpt"
    assert canonical_chat_command("--chat-ollama") == "--chat-ollama"
    assert canonical_chat_command("--ollama") == "--chat-ollama"
    assert canonical_chat_command("--chat-openai") == "--chat-open-ai"
    # Future providers remain model/channel adapters, not new session owners.
    assert canonical_chat_command("--chat-future-provider") == "--chat-future-provider"


def test_model_channel_contract_is_allowlisted_and_does_not_publish_values() -> None:
    payload = normalize_model_channel_config(
        {
            "model_adapter": "ollama",
            "model_name": "local-private-model-name",
            "model_api_base": "http://127.0.0.1:11434",
            "model_timeout_seconds": 180.0,
            "model_max_output_tokens": 2048,
        }
    )
    metadata = model_channel_public_metadata(payload)

    assert metadata["configured"] is True
    assert metadata["contains_credentials"] is False
    assert set(metadata["fields"]) == set(payload)
    assert "local-private-model-name" not in repr(metadata)
    assert "127.0.0.1" not in repr(metadata)

    with pytest.raises(ValueError, match="model_channel_config_unknown_fields"):
        normalize_model_channel_config({"api_key": "must-never-cross-runtime-boundary"})
    with pytest.raises(ValueError, match="model_channel_config_unknown_fields"):
        normalize_model_channel_config({"authorization": "Bearer secret"})


def test_daemon_request_fingerprint_binds_command_and_model_channel() -> None:
    common = {
        "user_text": "hej",
        "session_id": "jazn-main",
        "no_carryover": False,
        "client": "regression",
    }
    base = runtime_daemon.daemon_chat_request_fingerprint(
        **common,
        command="--chat",
        model_channel_config={},
    )
    gpt = runtime_daemon.daemon_chat_request_fingerprint(
        **common,
        command="--chat-gpt",
        model_channel_config={},
    )
    ollama_a = runtime_daemon.daemon_chat_request_fingerprint(
        **common,
        command="--chat-ollama",
        model_channel_config={"model_adapter": "ollama", "model_name": "a"},
    )
    ollama_b = runtime_daemon.daemon_chat_request_fingerprint(
        **common,
        command="--chat-ollama",
        model_channel_config={"model_adapter": "ollama", "model_name": "b"},
    )

    assert len({base, gpt, ollama_a, ollama_b}) == 4


def test_daemon_job_snapshot_exposes_model_fields_not_private_values() -> None:
    job = runtime_daemon.DaemonChatJob(
        request_id="request-1",
        user_text="hej",
        input_field="message",
        session_id="jazn-main",
        no_carryover=False,
        client="regression",
        command="--chat-ollama",
        model_channel_config={
            "model_adapter": "ollama",
            "model_name": "private-model-value",
            "model_api_base": "http://127.0.0.1:11434",
        },
    )
    snapshot = job.snapshot(include_result=False)

    assert snapshot["command"] == "--chat-ollama"
    assert snapshot["model_channel"]["configured"] is True
    assert snapshot["model_channel"]["contains_credentials"] is False
    assert "private-model-value" not in repr(snapshot["model_channel"])
    assert "127.0.0.1" not in repr(snapshot["model_channel"])


def test_daemon_conversation_session_is_transport_only_and_close_does_not_stop_runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []

    def fake_chat_daemon(_config: Any, user_text: str, **kwargs: Any) -> dict[str, Any]:
        calls.append({"user_text": user_text, **kwargs})
        return {"ok": True, "final_visible_text": "odpowiedź"}

    monkeypatch.setattr(daemon_session_module, "chat_daemon", fake_chat_daemon)
    session = DaemonConversationSession(
        JaznConfig(root=tmp_path),
        command="--chat-ollama",
        model_channel_config={"model_adapter": "ollama", "model_name": "test"},
    )

    result = session.process_user_text("hej", request_id="turn-1")
    session.close()

    assert len(calls) == 1
    assert calls[0]["session_id"] == "jazn-main"
    assert calls[0]["command"] == "--chat-ollama"
    assert calls[0]["request_id"] == "turn-1"
    assert result["conversation_session_authority"]["owner"] == "persistent_daemon"
    assert result["conversation_session_authority"]["adapter_is_session_owner"] is False
    assert result["conversation_session_authority"]["client_close_stops_runtime"] is False
    assert session.usable is False


def test_no_carryover_resets_daemon_authority_once_then_preserves_turn_continuity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []

    def fake_chat_daemon(_config: Any, user_text: str, **kwargs: Any) -> dict[str, Any]:
        calls.append({"user_text": user_text, **kwargs})
        return {
            "ok": True,
            "accepted": True,
            "final_visible_text": user_text,
        }

    monkeypatch.setattr(daemon_session_module, "chat_daemon", fake_chat_daemon)
    session = DaemonConversationSession(
        JaznConfig(root=tmp_path),
        session_id="clean-session",
        no_carryover=True,
        command="--chat",
    )

    session.process_user_text("pierwsza")
    session.process_user_text("druga")

    assert [call["reset_session"] for call in calls] == [True, False]
    assert {call["session_id"] for call in calls} == {"clean-session"}


def test_daemon_reset_session_replaces_existing_worker_once(tmp_path: Path) -> None:
    cfg = JaznConfig(root=tmp_path)
    server = runtime_daemon.JaznDaemonServer(
        ("127.0.0.1", 0),
        runtime_daemon.JaznDaemonHandler,
        config=cfg,
        marker_path=tmp_path / "workspace_runtime" / "JAZN_ACTIVE_RUNTIME.json",
        session_factory=_EchoSession,
        execution_timeout_seconds=1.0,
        hard_worker_process_isolation=False,
    )
    try:
        first, _ = server.get_session(
            "clean-session",
            no_carryover=False,
            command="--chat",
        )
        reset, _ = server.get_session(
            "clean-session",
            no_carryover=True,
            command="--chat",
            reset_session=True,
        )
        reused, _ = server.get_session(
            "clean-session",
            no_carryover=True,
            command="--chat",
            reset_session=False,
        )

        assert reset is not first
        assert reused is reset
    finally:
        server.close_sessions()
        server.server_close()


def test_terminal_shell_exit_disconnects_daemon_client_without_claiming_runtime_shutdown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        daemon_session_module,
        "chat_daemon",
        lambda *_args, **_kwargs: {"ok": True, "final_visible_text": "ok"},
    )
    session = DaemonConversationSession(JaznConfig(root=tmp_path))
    output = StringIO()
    shell = LatkaRuntimeShell(
        session,
        stdin=StringIO(""),
        stdout=output,
        session_id=session.state.session_id,
    )

    assert shell.lifecycle.session_owner == "persistent_daemon"
    assert shell.lifecycle.shutdown_when_loop_exits is False
    assert shell.lifecycle.engine_reused_between_turns is True
    assert shell.do_exit("") is True
    assert session.usable is True
    assert "Daemon" in output.getvalue() or "daemon" in output.getvalue()


class _EchoSession:
    def __init__(self, _config: Any, **kwargs: Any) -> None:
        self.state = SimpleNamespace(session_id=kwargs.get("session_id"))

    def process_user_text(self, user_text: str, **_kwargs: Any) -> dict[str, Any]:
        return {"ok": True, "final_visible_text": user_text}

    def close(self) -> None:
        return None


def test_chatgpt_host_contract_is_selected_by_command_not_transport_client_name(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from latka_jazn.core import chat_command_contract

    observed: list[dict[str, Any]] = []

    def fake_attach(
        result: dict[str, Any],
        *,
        config: Any,
        user_text: str,
        chat_bridge_meta: dict[str, Any],
    ) -> None:
        del config
        observed.append(
            {
                "user_text": user_text,
                "client": chat_bridge_meta.get("client"),
            }
        )
        result["chatgpt_host_bridge"] = {"phase": "runtime_final_available"}

    monkeypatch.setattr(chat_command_contract, "attach_chatgpt_host_contract", fake_attach)
    cfg = JaznConfig(root=tmp_path)
    server = runtime_daemon.JaznDaemonServer(
        ("127.0.0.1", 0),
        runtime_daemon.JaznDaemonHandler,
        config=cfg,
        marker_path=tmp_path / "workspace_runtime" / "JAZN_ACTIVE_RUNTIME.json",
        session_factory=_EchoSession,
        execution_timeout_seconds=1.0,
        hard_worker_process_isolation=False,
    )
    server.write_marker = lambda **_kwargs: {"manifest_current_sha256": None}  # type: ignore[method-assign]
    try:
        job, created, error = server.submit_chat_job(
            user_text="hej",
            input_field="message",
            session_id="jazn-main",
            no_carryover=False,
            client="chatgpt_bridge",
            command="--chat-gpt",
            request_id="host-contract-command-test",
        )
        assert created is True
        assert error is None
        assert job is not None
        assert job.done_event.wait(3.0)
        assert job.status == "completed"
        assert observed == [{"user_text": "hej", "client": "chatgpt_bridge"}]
    finally:
        server.close_sessions()
        server.server_close()


def test_model_timeout_extends_daemon_job_budget_without_changing_session_owner(
    tmp_path: Path,
) -> None:
    cfg = JaznConfig(root=tmp_path)
    server = runtime_daemon.JaznDaemonServer(
        ("127.0.0.1", 0),
        runtime_daemon.JaznDaemonHandler,
        config=cfg,
        marker_path=tmp_path / "workspace_runtime" / "JAZN_ACTIVE_RUNTIME.json",
        session_factory=_EchoSession,
        execution_timeout_seconds=1.0,
        hard_worker_process_isolation=False,
    )
    server.write_marker = lambda **_kwargs: {"manifest_current_sha256": None}  # type: ignore[method-assign]
    try:
        job, created, error = server.submit_chat_job(
            user_text="hej",
            input_field="message",
            session_id="jazn-main",
            no_carryover=False,
            client="ollama_local_bridge",
            command="--chat-ollama",
            model_channel_config={
                "model_adapter": "ollama",
                "model_timeout_seconds": 120.0,
            },
            request_id="model-timeout-budget-test",
        )
        assert created is True
        assert error is None
        assert job is not None
        assert job.execution_timeout_seconds is not None
        assert job.execution_timeout_seconds >= 150.0
        assert job.done_event.wait(3.0)
    finally:
        server.close_sessions()
        server.server_close()
