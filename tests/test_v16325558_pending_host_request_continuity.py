from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

import main as main_module
from latka_jazn.config import JaznConfig
from latka_jazn.core import chat_command_contract
from latka_jazn.core.chat_command_contract import (
    attach_chatgpt_host_contract,
    build_chatgpt_host_bridge_turn_contract,
    build_chatgpt_host_presentation_packet,
)
from latka_jazn.core.chatgpt_host_pending_store import (
    HostRequestStoreError,
    persist_pending_host_request,
)
from latka_jazn.core.host_visible_finalization import sha256_host_visible_text

SAMPLE = datetime(2026, 9, 10, 0, 15, 0, tzinfo=timezone.utc)
SAMPLE_ISO = SAMPLE.isoformat()
HEADER = f"🕒 {SAMPLE.astimezone(ZoneInfo('Europe/Warsaw')):%Y-%m-%d %H:%M:%S}"


def _host_generation_payload(*, turn_id: str = "turn-host-58") -> dict:
    trace_id = f"trace-{turn_id}"
    return {
        "runtime_version": "test-version",
        "trace": {
            "turn_id": turn_id,
            "trace_id": trace_id,
            "timestamp_header": HEADER,
            "timezone": "Europe/Warsaw",
        },
        "conversation_decision": {
            "handler_name": "RuntimeTurnTruthGate",
            "route": "ordinary_dialogue",
            "detected_user_intent": "short_free_dialogue",
            "requires_host_model": True,
            "timestamp_contract": {
                "timezone": "Europe/Warsaw",
                "sample_iso": SAMPLE_ISO,
                "source": "local_fallback",
                "trusted": False,
            },
        },
        "runtime_turn_contract": {
            "turn_id": turn_id,
            "trace_id": trace_id,
            "handler_name": "RuntimeTurnTruthGate",
            "requires_host_model": True,
            "fallback_classification": "cannot_answer_directly",
            "validation": {"accepted": True},
        },
        "final_response_contract": {
            "turn_id": turn_id,
            "trace_id": trace_id,
            "runtime_version": "test-version",
            "requires_host_model": True,
            "timestamp_header": HEADER,
            "timezone": "Europe/Warsaw",
            "timestamp_sample_iso": SAMPLE_ISO,
            "timestamp_source": "local_fallback",
            "timestamp_trusted": False,
            "author_id": "latka_runtime",
            "author_label": "Łatka",
            "author_source": "jazn_runtime",
            "state_emoticon": "🌿",
        },
        "runtime_truth_gate": {
            "ok": True,
            "normal_response_allowed": False,
            "errors": ["model_guided_speech_required"],
        },
    }


def _daemon_owned_phase_one(
    root: Path,
    *,
    user_text: str = "Heyo.",
    request_id: str = "daemon-request-58",
) -> dict:
    runtime = _host_generation_payload()
    runtime["daemon"] = {"request_id": request_id}
    attach_chatgpt_host_contract(
        runtime,
        config=JaznConfig(root=root),
        user_text=user_text,
        chat_bridge_meta={
            "client": "chatgpt_daemon_bridge",
            "input_kind": "daemon_http",
            "input_field": "json.message",
            "request_id": request_id,
            "process_lifecycle": "persistent_daemon_async_job",
        },
    )
    bridge = runtime["chatgpt_host_bridge"]
    assert bridge["phase"] == "host_visible_generation_requested"
    assert bridge["pending_request_persisted"] is True
    return runtime


def _forbid_phase_one_remint(*_args, **_kwargs):
    raise AssertionError("persisted daemon phase-1 must be reused, not reminted")


def test_completed_daemon_presentation_reuses_persisted_phase_one(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_text = "Heyo."
    request_id = "daemon-request-poll-58"
    runtime = _daemon_owned_phase_one(tmp_path, user_text=user_text, request_id=request_id)
    original_bridge = deepcopy(runtime["chatgpt_host_bridge"])

    monkeypatch.setattr(
        main_module,
        "build_chatgpt_host_bridge_turn_contract",
        _forbid_phase_one_remint,
    )
    monkeypatch.setattr(
        chat_command_contract,
        "build_chatgpt_host_bridge_turn_contract",
        _forbid_phase_one_remint,
    )

    presented = main_module._prepare_chatgpt_daemon_presentation(
        cfg=JaznConfig(root=tmp_path),
        payload={
            "ok": True,
            "done": True,
            "request_id": request_id,
            "job_status": "awaiting_host_finalization",
            "user_text": user_text,
            "user_text_sha256": sha256_host_visible_text(user_text),
            "result": runtime,
        },
        request_id=request_id,
        user_text=user_text,
    )

    bridge = presented["chatgpt_host_bridge"]
    assert bridge["phase"] == "host_visible_generation_requested"
    assert bridge["pending_request_persisted"] is True
    assert bridge["host_request_contract_hash"] == original_bridge["host_request_contract_hash"]
    assert bridge["daemon_request_id"] == request_id
    packet = build_chatgpt_host_presentation_packet(presented)
    assert packet["action"] == "generate_then_finalize"


def test_chatgpt_daemon_fast_path_reuses_daemon_owned_phase_one(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    user_text = "Heyo."
    request_id = "daemon-request-fast-58"
    runtime = _daemon_owned_phase_one(tmp_path, user_text=user_text, request_id=request_id)
    original_hash = runtime["chatgpt_host_bridge"]["host_request_contract_hash"]
    marker = tmp_path / "JAZN_ACTIVE_RUNTIME.json"
    marker.write_text("{}\n", encoding="utf-8")

    monkeypatch.setattr(main_module, "_chatgpt_daemon_marker_path", lambda _cfg: marker)
    monkeypatch.setattr(
        main_module,
        "status_daemon",
        lambda *_args, **_kwargs: {
            "active_state": "active_trusted",
            "endpoint_reachable": True,
        },
    )
    monkeypatch.setattr(main_module, "chat_daemon", lambda *_args, **_kwargs: deepcopy(runtime))
    monkeypatch.setattr(
        main_module,
        "build_chatgpt_host_bridge_turn_contract",
        _forbid_phase_one_remint,
    )
    monkeypatch.setattr(
        chat_command_contract,
        "build_chatgpt_host_bridge_turn_contract",
        _forbid_phase_one_remint,
    )

    exit_code = main_module._try_chat_gpt_one_shot_via_daemon(
        cfg=JaznConfig(root=tmp_path),
        text=user_text,
        session_id="chatgpt-bridge-default",
        no_carryover=False,
        host="127.0.0.1",
        port=8787,
        timeout=30.0,
        output_mode="host_packet",
        request_id=request_id,
        wait_budget=30.0,
    )

    assert exit_code == 0
    packet = json.loads(capsys.readouterr().out)
    assert packet["action"] == "generate_then_finalize"
    assert packet["chatgpt_host_bridge"]["host_request_contract_hash"] == original_hash
    assert packet["daemon_request_id"] == request_id


def test_true_different_contract_for_same_turn_still_fails_closed(tmp_path: Path) -> None:
    runtime = _host_generation_payload(turn_id="turn-conflict-58")
    runtime["daemon"] = {"request_id": "daemon-conflict-58"}
    first = build_chatgpt_host_bridge_turn_contract(
        runtime,
        user_text="pierwsza wiadomość",
        chat_bridge_meta={},
    )
    persist_pending_host_request(tmp_path, first)

    different = build_chatgpt_host_bridge_turn_contract(
        runtime,
        user_text="inna wiadomość",
        chat_bridge_meta={},
    )
    assert different["host_request_contract_hash"] != first["host_request_contract_hash"]

    with pytest.raises(HostRequestStoreError, match="pending_host_request_conflict"):
        persist_pending_host_request(tmp_path, different)
