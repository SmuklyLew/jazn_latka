from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from latka_jazn.core.conversation_runtime_convergence import (
    ConversationRunner,
    ConversationTurnLedger,
    ConversationTurnState,
    advance_turn_state,
    build_host_finalized_turn_state,
    build_linguistic_turn_frame,
    exact_input_sha256,
    install_conversation_runner_class,
    new_turn_state_contract,
    validate_linguistic_turn_frame,
    validate_turn_state_contract,
)
from latka_jazn.version import PACKAGE_RELEASE_NAME, PACKAGE_VERSION


def test_exact_input_fingerprint_preserves_surface_differences() -> None:
    assert exact_input_sha256("Hej") == hashlib.sha256("Hej".encode("utf-8")).hexdigest()
    assert exact_input_sha256("Hej") != exact_input_sha256("hej")
    assert exact_input_sha256("Hej") != exact_input_sha256("Hej ")


def test_turn_state_machine_rejects_illegal_visible_bypass() -> None:
    contract = new_turn_state_contract(
        session_id="session-a",
        request_id="request-a",
        turn_id="turn-a",
        trace_id="trace-a",
        user_text="Hej",
    )
    with pytest.raises(ValueError, match="invalid conversation turn transition"):
        advance_turn_state(
            contract,
            ConversationTurnState.VISIBLE_COMMITTED,
            reason="bypass",
        )


def test_host_finalized_state_has_single_accepted_visible_terminal() -> None:
    state = build_host_finalized_turn_state(
        session_id="session-a",
        request_id="request-a",
        turn_id="turn-a",
        trace_id="trace-a",
        user_text_sha256=exact_input_sha256("Hej"),
    )
    validation = validate_turn_state_contract(state)
    assert validation["ok"] is True
    assert validation["visible_commit_ready"] is True
    assert state["state"] == "visible_committed"
    assert [item["state_after"] for item in state["transitions"]].count("visible_committed") == 1


def test_linguistic_frame_binds_nlp_memory_task_state_and_runtime_ownership() -> None:
    model_context = {
        "user_text": "Przypomnij mi naszą rozmowę",
        "nlg_plan": {
            "answer_kind": "natural_dialogue",
            "memory_policy": "required_grounded_payload",
            "source_policy": "runtime_only",
        },
        "operational_thought_frame": {
            "dialogue_task_state": {"active_goal": "memory_recall", "step": 2},
        },
        "full_canon_model_context": {"immutable_canon_sha256": "a" * 64},
        "allowed_memory_items": [
            {"item_id": "memory-1", "excerpt": "bounded evidence"},
        ],
        "required_truth_boundaries": ["grounded_only"],
        "forbidden_claims": ["invented_memory"],
        "output_instructions": ["Odpowiedz po polsku."],
    }
    frame = build_linguistic_turn_frame(
        model_context,
        detected_intent="self_memory_recall",
        route="self_memory_recall",
    )
    assert validate_linguistic_turn_frame(frame)["ok"] is True
    assert frame["dialogue_task_state"]["active_goal"] == "memory_recall"
    assert frame["allowed_memory_item_ids"] == ["memory-1"]
    assert frame["runtime_owns_session_state"] is True
    assert frame["runtime_owns_memory"] is True
    assert frame["runtime_owns_finalization"] is True
    assert frame["provider_is_language_executor_only"] is True

    tampered = dict(frame)
    tampered["route"] = "bypass"
    assert validate_linguistic_turn_frame(tampered)["ok"] is False


def test_turn_ledger_persists_only_lineage_hashes_and_state(tmp_path: Path) -> None:
    secret_text = "prywatna dokładna treść użytkownika"
    state = build_host_finalized_turn_state(
        session_id="session-a",
        request_id="request-a",
        turn_id="turn-a",
        trace_id="trace-a",
        user_text_sha256=exact_input_sha256(secret_text),
    )
    status = ConversationTurnLedger(tmp_path).append(state)
    assert status["ok"] is True
    text = (tmp_path / "workspace_runtime" / "conversation_turn_state.jsonl").read_text(encoding="utf-8")
    record = json.loads(text)
    assert secret_text not in text
    assert record["input_sha256"] == exact_input_sha256(secret_text)
    assert record["state"] == "visible_committed"


def test_runner_install_converges_runtime_session_and_daemon_factory(monkeypatch) -> None:
    from latka_jazn.core import runtime_session as runtime_session_module

    class FakeServer:
        def __init__(self, *, session_factory=object):
            self.session_factory = session_factory

    fake_daemon = SimpleNamespace(
        JaznRuntimeSession=object,
        JaznDaemonServer=FakeServer,
    )
    monkeypatch.setattr(runtime_session_module, "JaznRuntimeSession", object)

    status = install_conversation_runner_class(runtime_daemon_module=fake_daemon)

    assert status["installed"] is True
    assert runtime_session_module.JaznRuntimeSession is ConversationRunner
    assert fake_daemon.JaznRuntimeSession is ConversationRunner
    assert FakeServer.__init__.__kwdefaults__["session_factory"] is ConversationRunner
    assert status["spawn_pickleable"] is True


def test_release_identity_marks_final_conversation_runtime_nlp_convergence() -> None:
    assert tuple(int(part) for part in PACKAGE_VERSION.split(".")) >= (16, 3, 25, 5, 69)
    assert "conversation-runtime" in PACKAGE_RELEASE_NAME
