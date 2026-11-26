"""F02: diagnostic-only bridge must still satisfy canonical input binding."""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from latka_jazn.config import JaznConfig
from latka_jazn.core import chat_command_contract as bridge
from latka_jazn.core.turn_authority_runtime_overlay import install_turn_authority_runtime_overlay


def test_transport_diagnostic_retains_valid_turn_binding_without_authorizing_generation(tmp_path: Path) -> None:
    install_turn_authority_runtime_overlay()
    message = "Synthetic exact input.\n"
    error = "model_request_timeout"
    result: dict[str, Any] = {
        "ok": False,
        "runtime_turn_contract": {
            "turn_id": "synthetic-turn", "trace_id": "synthetic-trace",
            "requires_host_model": True, "fallback_classification": "cannot_answer_directly",
        },
        "conversation_decision": {
            "model_executor_preflight": {"executor": "local_model"},
            "model_generated": False,
            "model_guided_synthesis": {"used": False, "adapter_response": {
                "provider": "ollama", "adapter_id": "local_llm_adapter",
                "status": "timeout", "generated": False,
                "transport": {"error_code": error, "attempts": [{
                    "status": "timeout", "error_code": error, "request_dispatched": True,
                }]},
            }},
        },
    }
    bridge.attach_chatgpt_host_contract(
        result, config=JaznConfig(root=tmp_path), user_text=message, chat_bridge_meta={},
    )
    contract = result["chatgpt_host_bridge"]
    assert contract["user_text_sha256"] == hashlib.sha256(message.encode("utf-8")).hexdigest()
    assert contract["turn_id"] == "synthetic-turn"
    assert contract["trace_id"] == "synthetic-trace"
    assert contract["turn_pipeline_validation"]["ok"] is True
    assert contract["turn_pipeline_contract"]["stages"]["visible_reply_authority"] == "blocked"
    assert contract["turn_pipeline_contract"]["stages"]["runtime_finalization"] == "blocked"
    assert contract["diagnostic_reason"] == error
    assert contract["host_must_generate_visible_reply"] is False
    assert "host_request_contract_hash" not in contract
    assert "host_generation_context" not in contract
    presentation = result["chatgpt_host_presentation"]
    assert presentation["action"] == "host_diagnostic"
    assert presentation["authorship_verified"] is False
    assert presentation["diagnostic_reason"] == error
    assert presentation["final_visible_text"] == ""
