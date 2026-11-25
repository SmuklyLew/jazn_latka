"""Durable host projection recovery preserves newer session state and generation."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from latka_jazn.config import JaznConfig
from latka_jazn.core import chat_command_contract as contract
from latka_jazn.core import runtime_session_state as session
from latka_jazn.core.chatgpt_host_pending_store import persist_pending_host_request
from latka_jazn.core.conversation_runner import ConversationRunner
from latka_jazn.tools.chatgpt_host_bridge_helper import build_chatgpt_host_visible_reply_payload
from test_finalization_crash_atomicity import _finalize
from test_host_finalized_session_continuity import _runtime_payload


def _bound_request(root: Path) -> dict[str, Any]:
    state = session.RuntimeSessionState.create(session_id="session-v154", source_client="chatgpt")
    store = session.RuntimeSessionStateStore(root)
    assert store.save(state, turn_count=2)["session_state_saved"]
    runtime = _runtime_payload(state)
    bridge = contract.build_chatgpt_host_bridge_turn_contract(runtime, user_text="Zgadzam się. Zacznij teraz.", chat_bridge_meta={})
    runtime["chatgpt_host_bridge"] = bridge
    persist_pending_host_request(root, bridge)
    body = "Z pamięci odpowiadam na tę samą turę; trop pozostaje ograniczony do tej finalizacji. Źródło i indeks mają tu wyłącznie status kontraktowy; granica prawdy: to nie pełne potwierdzenie. Nie będę zastępować tej odpowiedzi aktualizacją."
    reply, missing = build_chatgpt_host_visible_reply_payload(runtime, final_text=body)
    assert not missing and reply is not None
    return reply


@pytest.mark.parametrize("damage", ["missing_pointer", "missing_primary", "newer_pointer", "newer_primary"])
def test_recovery_republishes_exact_checkpoint_without_rewinding(
    tmp_path: Path, damage: str,
) -> None:
    reply = _bound_request(tmp_path)
    result, errors = _finalize(tmp_path, reply)
    assert result is not None and not errors
    assert result["session_continuity_persistence"]["saved"]
    store = session.RuntimeSessionStateStore(tmp_path)
    state = store.load_or_create(session_id="session-v154")
    primary = store.path
    primary_bytes = primary.read_bytes()
    checkpoint = json.loads(primary_bytes)["_continuity"]
    assert checkpoint["host_finalization_projection"]["turn_id"] == reply["turn_id"]
    if damage == "missing_pointer":
        store.latest_path.unlink()
    elif damage == "missing_primary":
        primary.unlink()
    elif damage == "newer_pointer":
        newer = session.RuntimeSessionState.create(session_id="newer", source_client="synthetic")
        newer.update(user_text="newer", visible_text="newer")
        assert session.RuntimeSessionStateStore(tmp_path).save(newer, turn_count=1)["session_state_saved"]
    else:
        state.update(user_text="newer", visible_text="newer")
        assert store.save(state, turn_count=4)["session_state_saved"]
        primary_bytes = primary.read_bytes()
    expected_latest = store.latest_path.read_bytes() if store.latest_path.exists() else primary_bytes
    recovered = ConversationRunner.recover_projection(config=JaznConfig(root=tmp_path), turn_id=reply["turn_id"])
    assert recovered["capture"]["projection_status"] == "published"
    assert recovered["conversation"]["ok"] is True
    assert recovered["session"]["saved"] is (damage != "newer_primary")
    assert primary.read_bytes() == primary_bytes
    assert store.latest_path.read_bytes() == expected_latest
    second = ConversationRunner.recover_projection(config=JaznConfig(root=tmp_path), turn_id=reply["turn_id"])
    assert second["session"]["saved"] is (damage != "newer_primary")
    assert primary.read_bytes() == primary_bytes
    assert store.latest_path.read_bytes() == expected_latest


def test_default_recovery_repairs_missing_conversation_and_session_projection(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    reply = _bound_request(tmp_path)
    with monkeypatch.context() as fault:
        def fail(**_kwargs: Any) -> dict[str, Any]:
            raise OSError("injected postcommit projection failure")
        fault.setattr(contract, "_commit_host_finalized_conversation_state", fail)
        fault.setattr(contract, "_commit_host_finalized_session_continuity", fail)
        result, errors = _finalize(tmp_path, reply)
    assert result is not None and not errors
    assert result["conversation_state_persistence"]["ok"] is False
    assert result["session_continuity_persistence"]["saved"] is False
    recovered = ConversationRunner.recover_projection(config=JaznConfig(root=tmp_path), turn_id=reply["turn_id"])
    assert recovered["capture"]["projection_status"] == "published"
    assert recovered["conversation"]["ok"] is True
    assert recovered["session"]["saved"] is True
    state = session.RuntimeSessionStateStore(tmp_path).load_or_create(session_id="session-v154")
    assert state.last_visible_text == result["final_visible_text"]
    assert state.last_user_text == "Zgadzam się. Zacznij teraz."
    replay, errors = _finalize(tmp_path, reply)
    assert replay is None and errors == ["host_request:host_request_replay_detected"]
