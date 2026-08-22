from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from latka_jazn.config import JaznConfig
from latka_jazn.core.chat_command_contract import (
    build_chatgpt_host_bridge_turn_contract,
    persist_chatgpt_host_visible_reply,
)
from latka_jazn.core.chatgpt_host_pending_store import persist_pending_host_request
from latka_jazn.core.host_visible_finalization import sha256_host_visible_text
from latka_jazn.core.runtime_session_state import RuntimeSessionState, RuntimeSessionStateStore


SAMPLE = datetime(2026, 8, 9, 12, 0, 0, tzinfo=timezone.utc)
HEADER = f"🕒 {SAMPLE.astimezone(ZoneInfo('Europe/Warsaw')):%Y-%m-%d %H:%M:%S}"


def _runtime_payload(state: RuntimeSessionState) -> dict:
    return {
        "runtime_version": "test-version",
        "session": state.to_dict(),
        "session_provenance": {"continuity_turn_count": 2},
        "wake_state_runtime": {"status": "ready", "ok": True, "snapshot_id": "wake-1", "snapshot_sha256": "w" * 64},
        "trace": {"turn_id": "turn-v154", "trace_id": "trace-v154", "timestamp_header": HEADER, "timezone": "Europe/Warsaw"},
        "conversation_decision": {
            "handler_name": "RuntimeTurnTruthGate",
            "route": "self_memory_recall",
            "detected_user_intent": "self_memory_recall_request",
            "requires_host_model": True,
            "dialogue_task_state": {"active_intent": "self_memory_recall_request", "execution_status": "active"},
            "timestamp_contract": {"timezone": "Europe/Warsaw", "sample_iso": SAMPLE.isoformat(), "source": "test", "trusted": True},
        },
        "runtime_turn_contract": {
            "turn_id": "turn-v154", "trace_id": "trace-v154", "handler_name": "RuntimeTurnTruthGate",
            "requires_host_model": True, "fallback_classification": "cannot_answer_directly", "validation": {"accepted": True},
        },
        "final_response_contract": {
            "turn_id": "turn-v154", "trace_id": "trace-v154", "runtime_version": "test-version",
            "requires_host_model": True, "timestamp_header": HEADER, "timezone": "Europe/Warsaw",
            "timestamp_sample_iso": SAMPLE.isoformat(), "timestamp_source": "test", "timestamp_trusted": True,
            "author_id": "latka_runtime", "author_label": "Łatka", "author_source": "jazn_runtime", "state_emoticon": "🌿",
        },
        "runtime_truth_gate": {"ok": True, "normal_response_allowed": False, "errors": ["model_guided_speech_required"], "degradations": []},
    }


def test_host_finalization_advances_durable_task_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    state = RuntimeSessionState.create(session_id="session-v154", source_client="chatgpt")
    store = RuntimeSessionStateStore(tmp_path)
    assert store.save(state, continuity_context={"status": "ready", "ok": True, "snapshot_id": "wake-1", "snapshot_sha256": "w" * 64}, turn_count=2)["session_state_saved"]
    runtime = _runtime_payload(state)
    bridge = build_chatgpt_host_bridge_turn_contract(runtime, user_text="Zgadzam się. Zacznij teraz.", chat_bridge_meta={})
    runtime["chatgpt_host_bridge"] = bridge
    persist_pending_host_request(tmp_path, bridge)

    class FakeEngine:
        def __init__(self, _config) -> None: pass
        def shutdown(self) -> None: pass
        def persist_final_visible_reply(self, **kwargs):
            return {"final_visible_text": kwargs["final_text"], "turn_id": kwargs["turn_id"], "trace_id": kwargs["trace_id"]}

    import latka_jazn.core.engine as engine_module
    monkeypatch.setattr(engine_module, "JaznEngine", FakeEngine)
    body = "Rozpoczynam pracę od źródeł."
    payload = {
        "type": "host_visible_reply",
        "turn_id": bridge["turn_id"], "trace_id": bridge["trace_id"],
        "host_request_contract_hash": bridge["host_request_contract_hash"],
        "timestamp_header": bridge["timestamp_header"], "timezone": bridge["timezone"],
        "timestamp_sample_iso": bridge["timestamp_sample_iso"], "timestamp_source": bridge["timestamp_source"],
        "timestamp_trusted": bridge["timestamp_trusted"], "author_id": bridge["author_id"],
        "author_label": bridge["author_label"], "author_source": bridge["author_source"], "state_emoticon": bridge["state_emoticon"],
        "final_text": body, "final_text_sha256": sha256_host_visible_text(body),
    }
    result, errors = persist_chatgpt_host_visible_reply(config=JaznConfig(root=tmp_path), payload=payload, chat_bridge_meta={}, contract={})
    assert errors == [] and result is not None
    assert result["session_continuity_persistence"]["saved"] is True
    reloaded = RuntimeSessionStateStore(tmp_path).load_or_create(session_id="session-v154", source_client="test")
    assert reloaded.last_user_text == "Zgadzam się. Zacznij teraz."
    assert reloaded.last_visible_text is not None
    assert reloaded.last_visible_text.startswith(HEADER)
    assert reloaded.last_intent == "self_memory_recall_request"
    assert reloaded.last_route == "self_memory_recall"
    assert reloaded.task_state["active_intent"] == "self_memory_recall_request"


def test_delayed_finalizer_does_not_overwrite_newer_session_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    state = RuntimeSessionState.create(session_id="session-race", source_client="chatgpt")
    store = RuntimeSessionStateStore(tmp_path)
    store.save(state, turn_count=0)
    runtime = _runtime_payload(state)
    runtime["session"]["session_id"] = "session-race"
    bridge = build_chatgpt_host_bridge_turn_contract(runtime, user_text="Zacznij teraz", chat_bridge_meta={})
    persist_pending_host_request(tmp_path, bridge)
    current = RuntimeSessionStateStore(tmp_path).load_or_create(session_id="session-race", source_client="chatgpt")
    current.update(user_text="Nowsza tura", visible_text="Nowsza odpowiedź", intent="greeting", route="greeting")
    RuntimeSessionStateStore(tmp_path).save(current, turn_count=1)

    class FakeEngine:
        def __init__(self, _config) -> None: pass
        def shutdown(self) -> None: pass
        def persist_final_visible_reply(self, **kwargs):
            return {"final_visible_text": kwargs["final_text"], "turn_id": kwargs["turn_id"], "trace_id": kwargs["trace_id"]}

    import latka_jazn.core.engine as engine_module
    monkeypatch.setattr(engine_module, "JaznEngine", FakeEngine)
    body = "Stara finalizacja."
    payload = {
        "type": "host_visible_reply", "turn_id": bridge["turn_id"], "trace_id": bridge["trace_id"],
        "host_request_contract_hash": bridge["host_request_contract_hash"], "timestamp_header": bridge["timestamp_header"],
        "timezone": bridge["timezone"], "timestamp_sample_iso": bridge["timestamp_sample_iso"],
        "timestamp_source": bridge["timestamp_source"], "timestamp_trusted": bridge["timestamp_trusted"],
        "author_id": bridge["author_id"], "author_label": bridge["author_label"], "author_source": bridge["author_source"],
        "state_emoticon": bridge["state_emoticon"], "final_text": body, "final_text_sha256": sha256_host_visible_text(body),
    }
    result, errors = persist_chatgpt_host_visible_reply(config=JaznConfig(root=tmp_path), payload=payload, chat_bridge_meta={}, contract={})
    assert errors == [] and result is not None
    assert result["session_continuity_persistence"]["saved"] is False
    assert result["session_continuity_persistence"]["status"] == "session_advanced_or_phase_one_checkpoint_missing"
    reloaded = RuntimeSessionStateStore(tmp_path).load_or_create(session_id="session-race", source_client="test")
    assert reloaded.last_user_text == "Nowsza tura"
