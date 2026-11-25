"""J-003/004: accepted-session provenance must be computed before each turn."""
from __future__ import annotations

from pathlib import Path

import pytest

from latka_jazn.config import JaznConfig
from latka_jazn.core.conversation_runner import ConversationRunner
from latka_jazn.core.conversation_state_store import ConversationStateStore
from latka_jazn.core.session_provenance import project_turn_session_load


def test_real_runner_distinguishes_new_session_and_in_process_reuse(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name, value in {
        "JAZN_RUNTIME_WORKSPACE_DIR": str(tmp_path / "workspace_runtime"),
        "JAZN_MEMORY_ROOT": str(tmp_path / "memory"),
        "JAZN_MEMORY_MODE": "off",
        "JAZN_MODEL_ADAPTER": "null",
        "JAZN_LLM_ROUTE": "off",
        "JAZN_NETWORK_TIME_FIRST": "0",
        "JAZN_NETWORK_TIME_IN_TURN": "0",
        "JAZN_ALLOW_NETWORK": "0",
        "JAZN_DICTIONARY_ALLOW_NETWORK": "0",
        "JAZN_MEMORY_SYNC_MODE": "off",
    }.items():
        monkeypatch.setenv(name, value)
    (tmp_path / "main.py").write_text("# isolated fixture\n", encoding="utf-8")
    runner = ConversationRunner(JaznConfig(root=tmp_path, memory_mode="off"), session_id="j003-j004")
    try:
        initial = dict(runner.state_store.last_load_metadata)
        first = runner.process_user_text("Jaka jest godzina?", process_reused=True)
        assert first["answer_ok"] is True
        assert first["canonical_persistence_ok"] is True
        assert first["conversation_state_persistence"]["ok"] is True
        a = first["session_provenance"]
        assert a["session_loaded_from"] == "new"
        assert a["session_reused"] is False
        assert a["process_reused"] is True
        assert a["session_history_count_before_turn"] == 0
        assert a["session_prior_accepted_turn_id"] is None

        second = runner.process_user_text(
            "Zacytuj pierwszych trzech słów mojej poprzedniej wiadomości.",
            process_reused=True,
        )
        assert second["answer_ok"] is True, second.get("runtime_truth_gate")
        assert second["canonical_persistence_ok"] is True
        assert second["conversation_state_persistence"]["ok"] is True
        assert second["conversation_decision"]["body"] == "Jaka jest godzina?"
        b = second["session_provenance"]
        assert b["session_loaded_from"] == "in_process"
        assert b["session_reused"] is True
        assert b["session_resurrected_from_disk"] is False
        assert b["session_initial_loaded_from"] == "new"
        assert b["session_reuse_evidence"] == "previous_locally_accepted_turn"
        assert b["session_prior_accepted_turn_id"] == first["trace"]["turn_id"]
        assert b["session_prior_accepted_trace_id"] == first["trace"]["trace_id"]
        assert b["session_history_count_before_turn"] == 1
        assert runner.state_store.last_load_metadata == initial
        assert runner.conversation_state_store.load_context_projection("j003-j004")["total_turn_count"] == 2
    finally:
        runner.close()


def test_history_reuse_is_not_checkpoint_resurrection_or_local_worker_reuse(tmp_path: Path) -> None:
    store = ConversationStateStore(tmp_path)
    assert store.append_finalized_turn(
        session_id="A", turn_id="accepted", trace_id="trace",
        user_text="synthetic input", assistant_text="synthetic answer", source="test",
    )["ok"] is True
    history = store.load_context_projection("A")
    load = {"session_loaded_from": "session_checkpoint", "session_resurrected_from_disk": True,
            "session_carryover_blocked": True, "session_checkpoint_integrity_verified": True,
            "continuity_checkpoint_sha256": "a" * 64}
    result = project_turn_session_load(
        session_id="A", initial_load_metadata=load, conversation_history=history,
        previous_user_text="synthetic input", previous_visible_text="synthetic answer",
        last_locally_accepted_turn_id=None, history_allowed=True,
    )
    assert result["session_loaded_from"] == "accepted_session_history"
    assert result["session_reused"] is True
    assert result["session_initial_resurrected_from_disk"] is True
    assert result["session_resurrected_from_disk"] is False
    assert result["session_input_checkpoint_sha256"] is None

    # Rejected/unknown checkpoint and identical ID cannot create evidence.
    for bad in (
        {**history, "invalid_record_count": 1},
        {**history, "session_id": "foreign"},
        store.load_context_projection("B"),
    ):
        result = project_turn_session_load(
            session_id="A", initial_load_metadata=load, conversation_history=bad,
            previous_user_text="synthetic input", previous_visible_text="synthetic answer",
            last_locally_accepted_turn_id="accepted", history_allowed=True,
        )
        assert result["session_reused"] is False
        assert result["session_resurrected_from_disk"] is False
    disabled = project_turn_session_load(
        session_id="A", initial_load_metadata=load, conversation_history=history,
        previous_user_text="synthetic input", previous_visible_text="synthetic answer",
        last_locally_accepted_turn_id="accepted", history_allowed=False,
    )
    assert disabled["session_reused"] is False
    assert disabled["session_loaded_from"] == "carryover_disabled"


def test_empty_or_unverified_checkpoint_has_no_accepted_session_credit(tmp_path: Path) -> None:
    from latka_jazn.core.runtime_session_state import RuntimeSessionStateStore
    import json

    first = RuntimeSessionStateStore(tmp_path)
    state = first.load_or_create(session_id="legacy")
    path = first._path_for_session(state.session_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state.to_dict()), encoding="utf-8")
    restored = RuntimeSessionStateStore(tmp_path)
    loaded = restored.load_or_create(session_id="legacy")
    status = restored.verify_loaded_continuity(loaded, None)
    assert status["carryover_allowed"] is False
    assert restored.last_load_metadata["session_reused"] is False
    result = project_turn_session_load(
        session_id="legacy", initial_load_metadata=restored.last_load_metadata,
        conversation_history=ConversationStateStore(tmp_path).load_context_projection("legacy"),
        previous_user_text=None, previous_visible_text=None,
        last_locally_accepted_turn_id=None, history_allowed=True,
    )
    assert result["session_reused"] is False
    assert result["session_resurrected_from_disk"] is False


@pytest.mark.parametrize(("unchanged", "count", "source"), [
    (True, 1, "session_checkpoint"),
    (False, 1, "accepted_session_history"),
    (True, 2, "accepted_session_history"),
])
def test_input_checkpoint_is_not_credited_after_worker_mutation_or_count_mismatch(
    tmp_path: Path, unchanged: bool, count: int, source: str,
) -> None:
    store = ConversationStateStore(tmp_path)
    assert store.append_finalized_turn(
        session_id="A", turn_id="accepted", trace_id="trace",
        user_text="same input", assistant_text="same answer", source="test",
    )["ok"] is True
    result = project_turn_session_load(
        session_id="A",
        initial_load_metadata={
            "session_loaded_from": "session_checkpoint",
            "session_resurrected_from_disk": True,
            "session_checkpoint_integrity_verified": True,
            "session_carryover_blocked": False,
            "continuity_checkpoint_sha256": "a" * 64,
            "continuity_turn_count": count,
        },
        conversation_history=store.load_context_projection("A"),
        previous_user_text="same input", previous_visible_text="same answer",
        last_locally_accepted_turn_id=None, history_allowed=True,
        checkpoint_state_unchanged=unchanged,
    )
    assert result["session_loaded_from"] == source
    assert result["session_reused"] is True
    assert result["session_resurrected_from_disk"] is (source == "session_checkpoint")
    assert result["session_input_checkpoint_sha256"] == (
        "a" * 64 if source == "session_checkpoint" else None
    )
