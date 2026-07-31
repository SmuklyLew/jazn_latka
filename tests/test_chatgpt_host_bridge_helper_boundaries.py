from __future__ import annotations

import io
import json
from typing import Any

import pytest

from latka_jazn.tools import chatgpt_host_bridge_helper


def test_loader_uses_the_top_level_packet_when_nested_bridge_is_not_an_object() -> None:
    packet: dict[str, Any] = {
        "phase": "host_visible_generation_requested",
        "host_must_generate_visible_reply": True,
        "chatgpt_host_bridge": ["invalid", "shape"],
    }

    loaded = chatgpt_host_bridge_helper.load_chatgpt_host_request_from_text(
        json.dumps(packet)
    )

    assert loaded == packet


def test_reply_builder_rejects_non_object_nested_contracts() -> None:
    packet: dict[str, Any] = {
        "chatgpt_host_bridge": {
            "phase": "host_visible_generation_requested",
            "host_reply_jsonl_shape": ["invalid", "shape"],
        },
        "runtime_turn_contract": ["invalid"],
        "final_response_contract": ["invalid"],
        "conversation_decision": ["invalid"],
    }

    payload, missing = (
        chatgpt_host_bridge_helper.build_chatgpt_host_visible_reply_payload(
            packet,
            final_text="Odpowiedź",
        )
    )

    assert payload is None
    assert "turn_id" in missing
    assert "timestamp_trusted" in missing


def test_helper_reports_unavailable_default_stdin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = io.StringIO()
    monkeypatch.setattr(chatgpt_host_bridge_helper.sys, "stdin", None)

    exit_code = chatgpt_host_bridge_helper.main(
        ["--build-only", "--final-text", "Odpowiedź"],
        stdout=output,
    )

    assert exit_code == 2
    error = json.loads(output.getvalue())
    assert error["error_code"] == "host_visible_reply_helper_failed"
    assert "stdin jest niedostępny" in error["error"]


def test_helper_fails_explicitly_when_default_stdout_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(chatgpt_host_bridge_helper.sys, "stdout", None)

    with pytest.raises(
        RuntimeError,
        match="chatgpt_host_bridge_stdout_unavailable",
    ):
        chatgpt_host_bridge_helper.main(
            ["--build-only", "--final-text", "Odpowiedź"],
            stdin=io.StringIO("{}"),
        )
