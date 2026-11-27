"""F04: a completed HTTP response can still be an incomplete model answer."""
from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

import pytest

from latka_jazn.config import JaznConfig
from latka_jazn.core import chat_command_contract as bridge
from latka_jazn.core.conversation_runner import _host_finalization_pending
from latka_jazn.core.model_transport_failure import (
    ollama_terminal_attempt_failure, ollama_transport_failure,
)
from latka_jazn.model_adapters.base import ModelAdapterRequest
from latka_jazn.model_adapters.local_llm_adapter import LocalLlmAdapter


@pytest.mark.parametrize("reason", ["length", "stop", None])
def test_provider_stop_reason_is_not_equivalent_to_transport_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, reason: str | None,
) -> None:
    calls: list[str] = []
    def reply(request: Any, *, timeout: float) -> io.BytesIO:
        calls.append(request.full_url)
        return io.BytesIO(json.dumps({
            "done": True, "done_reason": reason, "model": "synthetic",
            "message": {"role": "assistant", "content": "Synthetic partial candidate"},
            "eval_count": 8, "prompt_eval_count": 100,
        }).encode("utf-8"))
    monkeypatch.setattr("latka_jazn.model_adapters.local_llm_adapter.urlopen", reply)
    adapter = LocalLlmAdapter(root=tmp_path, model="synthetic", max_output_tokens=8)
    result = adapter.generate(ModelAdapterRequest(prompt="synthetic", metadata={"allow_non_polish": True}))
    assert calls == ["http://127.0.0.1:11434/api/chat"]
    assert adapter.describe()["model_transport_circuit"]["state"] == "closed"
    assert result.transport["attempts"][0]["done_reason"] == reason
    assert result.transport["attempts"][0]["eval_count"] == 8
    assert ollama_transport_failure(result.to_dict()) is None
    if reason != "length":
        assert result.generated and result.status == "completed"
        assert ollama_terminal_attempt_failure(result.to_dict()) is None
        return
    assert result.status == "output_limit_reached"
    assert not result.generated and not result.text
    assert result.status_snapshot is not None and result.status_snapshot.endpoint_reachable is True
    assert result.transport["retry_count"] == 0
    evidence = ollama_terminal_attempt_failure(result.to_dict())
    assert evidence is not None
    assert evidence["failure_kind"] == "generation_limit"
    assert evidence["automatic_retry_allowed"] is False
    assert "Synthetic partial candidate" not in repr(result.to_dict())
    payload: dict[str, Any] = {
        "ok": False, "answer_ok": False,
        "runtime_turn_contract": {
            "turn_id": "synthetic-turn", "trace_id": "synthetic-trace",
            "requires_host_model": True, "fallback_classification": "cannot_answer_directly",
        },
        "conversation_decision": {
            "model_executor_preflight": {"executor": "local_model"},
            "model_generated": False,
            "model_guided_synthesis": {"used": False, "adapter_response": result.to_dict()},
        },
    }
    assert _host_finalization_pending(payload, can_continue=True) == (False, [])
    bridge.attach_chatgpt_host_contract(payload, config=JaznConfig(root=tmp_path),
                                       user_text="synthetic", chat_bridge_meta={})
    assert payload["chatgpt_host_bridge"]["host_must_generate_visible_reply"] is False
    assert payload["chatgpt_host_presentation"]["action"] == "host_diagnostic"
    assert payload["chatgpt_host_presentation"]["diagnostic_reason"] == "model_output_limit_reached"
    assert payload["chatgpt_host_presentation"]["final_visible_text"] == ""
