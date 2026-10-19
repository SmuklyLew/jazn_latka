from __future__ import annotations

import io
from pathlib import Path
from typing import Any

import pytest

from latka_jazn.config import JaznConfig
from latka_jazn.core import chat_command_contract


def test_cli_warning_updates_the_existing_string_keyed_trace() -> None:
    trace: dict[str, Any] = {"turn_id": "turn-1"}
    result: dict[str, Any] = {"trace": trace}
    warning: dict[str, Any] = {
        "original_user_text": "wiadomość --final-only",
        "classification_text": "wiadomość",
        "code": "cli_flag_after_separator",
    }

    chat_command_contract.attach_cli_flag_warning(result, warning)

    assert result["trace"] is trace
    assert trace["chat_bridge_original_user_text"] == "wiadomość --final-only"
    assert trace["chat_bridge_classification_text"] == "wiadomość"
    assert trace["chat_bridge_input_warning_code"] == "cli_flag_after_separator"


def test_cli_warning_rejects_a_non_json_trace_shape() -> None:
    result: dict[str, Any] = {"trace": {1: "invalid JSON object key"}}
    warning: dict[str, Any] = {
        "original_user_text": "wiadomość --final-only",
        "classification_text": "wiadomość",
        "code": "cli_flag_after_separator",
    }

    chat_command_contract.attach_cli_flag_warning(result, warning)

    assert result["trace"] == {
        "chat_bridge_original_user_text": "wiadomość --final-only",
        "chat_bridge_classification_text": "wiadomość",
        "chat_bridge_input_warning_code": "cli_flag_after_separator",
    }


def test_jsonl_bridge_fails_explicitly_when_default_stdin_is_unavailable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(chat_command_contract.sys, "stdin", None)

    with pytest.raises(RuntimeError, match="chat_bridge_stdin_unavailable"):
        chat_command_contract.run_jsonl_chat_bridge(
            config=JaznConfig(root=tmp_path),
            session_id=None,
            no_carryover=False,
            command="--chat-gpt",
            stdout=io.StringIO(),
        )


def test_jsonl_bridge_fails_explicitly_when_default_stdout_is_unavailable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(chat_command_contract.sys, "stdout", None)

    with pytest.raises(RuntimeError, match="chat_bridge_stdout_unavailable"):
        chat_command_contract.run_jsonl_chat_bridge(
            config=JaznConfig(root=tmp_path),
            session_id=None,
            no_carryover=False,
            command="--chat-gpt",
            stdin=io.StringIO(),
        )
