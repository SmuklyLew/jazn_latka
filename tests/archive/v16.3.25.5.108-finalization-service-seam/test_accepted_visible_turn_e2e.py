from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

import main as main_module
from latka_jazn.config import JaznConfig
from latka_jazn.core.chat_command_contract import (
    attach_chatgpt_host_contract,
    build_chatgpt_host_presentation_packet,
    persist_chatgpt_host_visible_reply,
)
from latka_jazn.core.host_visible_finalization import sha256_host_visible_text
from latka_jazn.tools.chatgpt_host_bridge_helper import build_chatgpt_host_visible_reply_payload

SAMPLE = datetime(2026, 9, 11, 0, 10, tzinfo=timezone.utc)
HEADER = f"🕒 {SAMPLE.astimezone(ZoneInfo('Europe/Warsaw')):%Y-%m-%d %H:%M:%S}"


def _runtime_payload() -> dict:
    return {
        "runtime_version": "test-v61",
        "trace": {"turn_id": "turn-v61-e2e", "trace_id": "trace-v61-e2e", "timestamp_header": HEADER, "timezone": "Europe/Warsaw"},
        "conversation_decision": {
            "handler_name": "RuntimeTurnTruthGate", "route": "ordinary_dialogue",
            "detected_user_intent": "short_free_dialogue", "requires_host_model": True,
            "timestamp_contract": {"timezone": "Europe/Warsaw", "sample_iso": SAMPLE.isoformat(), "source": "test", "trusted": True},
        },
        "runtime_turn_contract": {
            "turn_id": "turn-v61-e2e", "trace_id": "trace-v61-e2e", "handler_name": "RuntimeTurnTruthGate",
            "requires_host_model": True, "fallback_classification": "cannot_answer_directly", "validation": {"accepted": True},
        },
        "final_response_contract": {
            "turn_id": "turn-v61-e2e", "trace_id": "trace-v61-e2e", "runtime_version": "test-v61",
            "requires_host_model": True, "timestamp_header": HEADER, "timezone": "Europe/Warsaw",
            "timestamp_sample_iso": SAMPLE.isoformat(), "timestamp_source": "test", "timestamp_trusted": True,
            "author_id": "latka_runtime", "author_label": "Łatka", "author_source": "jazn_runtime", "state_emoticon": "🌿",
        },
        "runtime_truth_gate": {"ok": True, "normal_response_allowed": False, "errors": ["model_guided_speech_required"], "degradations": []},
        "daemon": {"request_id": "request-v61-e2e"},
    }


def test_phase_ready_to_accepted_visible_final_e2e(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    user_text = "Czy każda widoczna tura przechodzi przez Jaźń?"
    cfg = JaznConfig(root=tmp_path)
    runtime = _runtime_payload()
    attach_chatgpt_host_contract(
        runtime, config=cfg, user_text=user_text,
        chat_bridge_meta={"client": "chatgpt_daemon_bridge", "request_id": "request-v61-e2e", "process_lifecycle": "persistent_daemon_async_job"},
    )
    original_hash = runtime["chatgpt_host_bridge"]["host_request_contract_hash"]

    presented = main_module._prepare_chatgpt_daemon_presentation(
        cfg=cfg,
        payload={
            "ok": True, "request_id": "request-v61-e2e", "done": False,
            "phase_result_ready": True, "job_status": "awaiting_host_finalization",
            "user_text": user_text, "user_text_sha256": sha256_host_visible_text(user_text), "result": runtime,
        },
        request_id="request-v61-e2e", user_text=user_text,
    )
    phase1 = build_chatgpt_host_presentation_packet(presented)
    assert phase1["action"] == "generate_then_finalize"
    assert phase1["accepted_visible_turn_ready"] is False
    assert phase1["chatgpt_host_bridge"]["host_request_contract_hash"] == original_hash
    assert presented["daemon_job"]["done"] is False
    assert presented["daemon_job"]["phase_result_ready"] is True

    class FakeEngine:
        def __init__(self, config: JaznConfig) -> None:
            self.config = config
        def shutdown(self) -> None:
            pass
        def persist_final_visible_reply(self, **kwargs):
            final = kwargs["final_text"]
            return {
                "final_visible_text": final,
                "final_text_sha256": sha256_host_visible_text(final),
                "turn_id": kwargs["turn_id"], "trace_id": kwargs["trace_id"],
                "timestamp_header": kwargs["timestamp_header"],
                "state_emoticon": kwargs["state_emoticon"],
                "author_label": kwargs["author_label"], "author_source": kwargs["author_source"],
                "envelope_present_in_final": True,
            }

    import latka_jazn.core.engine as engine_module
    monkeypatch.setattr(engine_module, "JaznEngine", FakeEngine)

    body = "Tak — ta odpowiedź staje się widoczna dopiero po zaakceptowanej finalizacji tej tury."
    reply, missing = build_chatgpt_host_visible_reply_payload(presented, final_text=body)
    assert missing == [] and reply is not None
    finalized, errors = persist_chatgpt_host_visible_reply(config=cfg, payload=reply, chat_bridge_meta={}, contract={})
    assert errors == [] and finalized is not None
    phase2 = build_chatgpt_host_presentation_packet(finalized)
    assert phase2["action"] == "display_exact"
    assert phase2["accepted_visible_turn_ready"] is True
    assert finalized["host_request_consumption"]["state"] == "consumed"
    assert phase2["final_visible_text"] == finalized["final_visible_text"]
    assert phase2["final_visible_text"].startswith(f"{HEADER}\n🌿 Łatka\n\n")

    replay, replay_errors = persist_chatgpt_host_visible_reply(config=cfg, payload=reply, chat_bridge_meta={}, contract={})
    assert replay is None
    assert any("host_request_replay_detected" in item or "host_request_already_consumed" in item for item in replay_errors)
