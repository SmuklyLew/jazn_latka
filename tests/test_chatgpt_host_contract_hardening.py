from __future__ import annotations

from datetime import datetime, timezone
import io
import json
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

import main as main_module
from latka_jazn.config import JaznConfig
from latka_jazn.core import chat_command_contract
from latka_jazn.core.chat_command_contract import (
    build_chatgpt_host_bridge_turn_contract,
    build_chatgpt_host_presentation_packet,
    extract_final_visible_text_from_result,
    persist_chatgpt_host_visible_reply,
    write_chat_bridge_payload,
)
from latka_jazn.core.chatgpt_host_pending_store import persist_pending_host_request
from latka_jazn.core.host_visible_finalization import sha256_host_visible_text
from latka_jazn.tools.chatgpt_host_bridge_helper import (
    ChatgptHostBridgeHelperError,
    build_chatgpt_host_visible_reply_payload,
    load_chatgpt_host_request_from_text,
)

SAMPLE = datetime(2026, 7, 31, 20, 0, 0, tzinfo=timezone.utc)
SAMPLE_ISO = SAMPLE.isoformat()
HEADER = f"🕒 {SAMPLE.astimezone(ZoneInfo('Europe/Warsaw')):%Y-%m-%d %H:%M:%S}"
FINAL = f"{HEADER}\n🌿 Łatka\n\nDokładny tekst.\n"


def _runtime_final_payload(*, integrity_valid: bool = True) -> dict:
    integrity = {"valid": integrity_valid, "text_sha256": sha256_host_visible_text(FINAL)}
    return {
        "runtime_version": "test-version",
        "final_visible_text": FINAL,
        "trace": {"turn_id": "turn-1", "trace_id": "trace-1", "timestamp_header": HEADER, "timezone": "Europe/Warsaw"},
        "conversation_decision": {"handler_name": "OrdinaryDialogueHandler", "route": "ordinary_dialogue"},
        "runtime_turn_contract": {
            "turn_id": "turn-1", "trace_id": "trace-1", "handler_name": "OrdinaryDialogueHandler",
            "requires_host_model": False, "validation": {"accepted": True},
        },
        "final_response_contract": {
            "turn_id": "turn-1", "trace_id": "trace-1", "requires_host_model": False,
            "timestamp_header": HEADER, "timezone": "Europe/Warsaw",
            "author_id": "latka_runtime", "author_label": "Łatka",
            "author_source": "jazn_runtime", "state_emoticon": "🌿",
            "final_visible_text": FINAL, "final_visible_integrity": integrity,
        },
        "final_visible_integrity": integrity,
        "final_visible_integrity_consensus": {"valid": integrity_valid, "mismatch": not integrity_valid},
        "runtime_truth_gate": {"ok": True, "normal_response_allowed": integrity_valid},
    }


def _host_generation_payload() -> dict:
    return {
        "runtime_version": "test-version",
        "trace": {"turn_id": "turn-host", "trace_id": "trace-host", "timestamp_header": HEADER, "timezone": "Europe/Warsaw"},
        "conversation_decision": {
            "handler_name": "RuntimeTurnTruthGate", "route": "greeting", "requires_host_model": True,
            "timestamp_contract": {"timezone": "Europe/Warsaw", "sample_iso": SAMPLE_ISO, "source": "local_fallback", "trusted": False},
        },
        "runtime_turn_contract": {
            "turn_id": "turn-host", "trace_id": "trace-host", "handler_name": "RuntimeTurnTruthGate",
            "requires_host_model": True, "fallback_classification": "cannot_answer_directly",
            "validation": {"accepted": True},
        },
        "final_response_contract": {
            "turn_id": "turn-host", "trace_id": "trace-host", "runtime_version": "test-version",
            "requires_host_model": True, "timestamp_header": HEADER, "timezone": "Europe/Warsaw",
            "timestamp_sample_iso": SAMPLE_ISO, "timestamp_source": "local_fallback", "timestamp_trusted": False,
            "author_id": "latka_runtime", "author_label": "Łatka", "author_source": "jazn_runtime", "state_emoticon": "🌿",
        },
        "runtime_truth_gate": {
            "ok": True,
            "normal_response_allowed": False,
            "errors": ["model_guided_speech_required"],
            "degradations": ["timestamp_untrusted", "timestamp_source_not_network"],
            "timestamp_degraded": True,
        },
    }


def test_one_shot_chatgpt_defaults_to_action_first_host_packet() -> None:
    assert main_module._bridge_text_output_mode(SimpleNamespace(chat_gpt_final_only=False, final_only=False), "Witaj") == "host_packet"
    assert main_module._bridge_text_output_mode(SimpleNamespace(chat_gpt_final_only=False, final_only=False), "") == "jsonl"
    assert main_module._bridge_text_output_mode(SimpleNamespace(chat_gpt_final_only=False, final_only=True), "Witaj") == "final_visible_text"


def test_runtime_final_is_displayed_only_after_all_presentation_gates() -> None:
    valid = _runtime_final_payload()
    valid["chatgpt_host_bridge"] = build_chatgpt_host_bridge_turn_contract(valid, user_text="test", chat_bridge_meta={})
    presentation = build_chatgpt_host_presentation_packet(valid)
    assert presentation["action"] == "display_exact"
    assert presentation["final_visible_text"] == FINAL

    output = io.StringIO()
    write_chat_bridge_payload(output, valid, output_mode="final_visible_text")
    assert output.getvalue() == FINAL

    invalid = _runtime_final_payload(integrity_valid=False)
    invalid["chatgpt_host_bridge"] = build_chatgpt_host_bridge_turn_contract(invalid, user_text="test", chat_bridge_meta={})
    output = io.StringIO()
    write_chat_bridge_payload(output, invalid, output_mode="final_visible_text")
    packet = json.loads(output.getvalue())
    assert packet["action"] == "host_diagnostic"
    assert packet["reason"] == "plain_text_blocked_by_host_presentation_gate"


def test_exact_final_extraction_preserves_leading_and_trailing_whitespace() -> None:
    text = "\n  tekst bez stripowania  \n"
    assert extract_final_visible_text_from_result({"final_visible_text": text}) == text


def test_host_request_is_bound_to_phase_one_and_replay_is_rejected(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    runtime = _host_generation_payload()
    bridge = build_chatgpt_host_bridge_turn_contract(runtime, user_text="Witaj", chat_bridge_meta={})
    runtime["chatgpt_host_bridge"] = bridge
    persist_pending_host_request(tmp_path, bridge)
    reply, missing = build_chatgpt_host_visible_reply_payload(runtime, final_text="Witaj, Krzysztofie.")
    assert missing == []
    assert reply is not None
    assert reply["host_request_contract_hash"] == bridge["host_request_contract_hash"]

    class FakeEngine:
        def __init__(self, config) -> None:
            self.config = config
        def shutdown(self) -> None:
            pass
        def persist_final_visible_reply(self, **kwargs):
            return {"final_visible_text": kwargs["final_text"], "turn_id": kwargs["turn_id"], "trace_id": kwargs["trace_id"]}

    import latka_jazn.core.engine as engine_module
    monkeypatch.setattr(engine_module, "JaznEngine", FakeEngine)
    cfg = JaznConfig(root=tmp_path)
    result, errors = persist_chatgpt_host_visible_reply(config=cfg, payload=reply, chat_bridge_meta={}, contract={})
    assert errors == []
    assert result is not None
    assert result["chatgpt_host_bridge"]["replay_protected"] is True

    replay, replay_errors = persist_chatgpt_host_visible_reply(config=cfg, payload=reply, chat_bridge_meta={}, contract={})
    assert replay is None
    assert replay_errors == ["host_request:host_request_replay_detected"]


def test_tampered_phase_two_envelope_is_rejected(tmp_path) -> None:
    runtime = _host_generation_payload()
    bridge = build_chatgpt_host_bridge_turn_contract(runtime, user_text="Witaj", chat_bridge_meta={})
    runtime["chatgpt_host_bridge"] = bridge
    persist_pending_host_request(tmp_path, bridge)
    reply, missing = build_chatgpt_host_visible_reply_payload(runtime, final_text="Witaj.")
    assert missing == [] and reply is not None
    reply["author_label"] = "Host ChatGPT"
    result, errors = persist_chatgpt_host_visible_reply(
        config=JaznConfig(root=tmp_path), payload=reply, chat_bridge_meta={}, contract={}
    )
    assert result is None
    assert errors == ["host_request_binding_mismatch:author_label"]


def test_helper_rejects_non_request_and_ambiguous_multiple_requests() -> None:
    with pytest.raises(ChatgptHostBridgeHelperError, match="Nie znaleziono pakietu"):
        load_chatgpt_host_request_from_text(json.dumps({"phase": "runtime_final_available"}))
    request = {"phase": "host_visible_generation_requested", "host_must_generate_visible_reply": True}
    with pytest.raises(ChatgptHostBridgeHelperError, match="niejednoznaczny"):
        load_chatgpt_host_request_from_text(json.dumps(request) + "\n" + json.dumps(request))


def test_daemon_pending_result_returns_poll_action_without_resubmitting(tmp_path) -> None:
    presented = main_module._prepare_chatgpt_daemon_presentation(
        cfg=JaznConfig(root=tmp_path),
        payload={
            "ok": False,
            "done": False,
            "error_code": "daemon_chat_pending",
            "request_id": "request-123",
            "job_status": "running",
        },
        request_id="request-123",
    )
    packet = build_chatgpt_host_presentation_packet(presented)
    assert packet["action"] == "poll_runtime"
    assert packet["daemon_request_id"] == "request-123"
    assert packet["poll_command"] == "python -X utf8 main.py --chat-gpt --daemon-result request-123"
    assert packet["must_not_claim_latka_voice"] is True


def test_completed_daemon_poll_uses_same_exact_display_gate(tmp_path) -> None:
    runtime = _runtime_final_payload()
    presented = main_module._prepare_chatgpt_daemon_presentation(
        cfg=JaznConfig(root=tmp_path),
        payload={
            "ok": True,
            "done": True,
            "request_id": "request-456",
            "job_status": "completed",
            "result": runtime,
        },
        request_id="request-456",
    )
    packet = build_chatgpt_host_presentation_packet(presented)
    assert packet["action"] == "display_exact"
    assert packet["final_visible_text"] == FINAL
    assert presented["daemon_job"]["request_id"] == "request-456"


def test_completed_daemon_poll_preserves_exact_user_text_for_host_generation(tmp_path) -> None:
    user_text = "Dlaczego nie mogłaś się obudzić po mojej pierwszej wiadomości?"
    runtime = _host_generation_payload()
    presented = main_module._prepare_chatgpt_daemon_presentation(
        cfg=JaznConfig(root=tmp_path),
        payload={
            "ok": True,
            "done": True,
            "request_id": "request-host",
            "job_status": "completed",
            "user_text": user_text,
            "user_text_sha256": sha256_host_visible_text(user_text),
            "result": runtime,
        },
        request_id="request-host",
    )
    bridge = presented["chatgpt_host_bridge"]
    assert bridge["phase"] == "host_visible_generation_requested"
    assert bridge["user_text_sha256"] == sha256_host_visible_text(user_text)
    assert bridge["pending_request_persisted"] is True


def test_completed_daemon_host_generation_fails_closed_without_user_text_binding(tmp_path) -> None:
    presented = main_module._prepare_chatgpt_daemon_presentation(
        cfg=JaznConfig(root=tmp_path),
        payload={
            "ok": True,
            "done": True,
            "request_id": "request-unbound",
            "job_status": "completed",
            "result": _host_generation_payload(),
        },
        request_id="request-unbound",
    )
    bridge = presented["chatgpt_host_bridge"]
    assert bridge["phase"] == "host_diagnostic_required"
    assert bridge["status"] == "daemon_user_text_binding_missing"
    assert bridge["host_must_generate_visible_reply"] is False


def test_failed_daemon_poll_cannot_fall_through_to_latka_voice(tmp_path) -> None:
    presented = main_module._prepare_chatgpt_daemon_presentation(
        cfg=JaznConfig(root=tmp_path),
        payload={"ok": False, "error_code": "chat_job_not_found", "request_id": "missing"},
        request_id="missing",
    )
    packet = build_chatgpt_host_presentation_packet(presented)
    assert packet["action"] == "host_diagnostic"
    assert packet["must_not_claim_latka_voice"] is True


def test_persistence_failure_becomes_indeterminate_and_cannot_replay(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    runtime = _host_generation_payload()
    bridge = build_chatgpt_host_bridge_turn_contract(runtime, user_text="Witaj", chat_bridge_meta={})
    runtime["chatgpt_host_bridge"] = bridge
    persist_pending_host_request(tmp_path, bridge)
    reply, missing = build_chatgpt_host_visible_reply_payload(runtime, final_text="Witaj.")
    assert missing == [] and reply is not None

    class FailingEngine:
        def __init__(self, config) -> None:
            self.config = config
        def shutdown(self) -> None:
            pass
        def persist_final_visible_reply(self, **kwargs):
            raise RuntimeError("append outcome unknown")

    import latka_jazn.core.engine as engine_module
    monkeypatch.setattr(engine_module, "JaznEngine", FailingEngine)
    result, errors = persist_chatgpt_host_visible_reply(
        config=JaznConfig(root=tmp_path), payload=reply, chat_bridge_meta={}, contract={}
    )
    assert result is None
    assert errors == ["host_persistence_indeterminate:RuntimeError"]

    replay, replay_errors = persist_chatgpt_host_visible_reply(
        config=JaznConfig(root=tmp_path), payload=reply, chat_bridge_meta={}, contract={}
    )
    assert replay is None
    assert replay_errors == ["host_request:host_request_persistence_indeterminate"]


def test_local_os_time_degradation_never_overrides_action_first_contract() -> None:
    runtime = _host_generation_payload()
    bridge = build_chatgpt_host_bridge_turn_contract(runtime, user_text="Jak się czujesz?", chat_bridge_meta={})
    runtime["chatgpt_host_bridge"] = bridge
    bridge["pending_request_persisted"] = True
    presentation = build_chatgpt_host_presentation_packet(runtime)

    assert presentation["action"] == "generate_then_finalize"
    assert presentation["runtime_checks"]["runtime_truth_gate_errors"] == ["model_guided_speech_required"]
    assert set(presentation["runtime_checks"]["runtime_truth_gate_degradations"]) == {
        "timestamp_untrusted",
        "timestamp_source_not_network",
    }
    assert presentation["runtime_checks"]["timestamp_degraded"] is True
    assert "nie powodem zmiany action" in presentation["host_instruction"]
