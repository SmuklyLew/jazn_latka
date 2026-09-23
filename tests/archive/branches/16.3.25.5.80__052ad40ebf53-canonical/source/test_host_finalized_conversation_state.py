from __future__ import annotations

from pathlib import Path

from latka_jazn.config import JaznConfig
from latka_jazn.core.chat_command_contract import (
    _canonical_mapping_sha256,
    _commit_host_finalized_conversation_state,
)
from latka_jazn.core.conversation_state_store import ConversationStateStore
from latka_jazn.version import schema_version


def _phase_one_commit() -> dict:
    return {
        "schema_version": schema_version("host_finalized_session_continuity_commit"),
        "session_id": "chatgpt-session",
        "turn_id": "turn-7",
        "trace_id": "trace-7",
        "source_client": "chatgpt_host",
        "user_text": "Co pamiętasz z tej rozmowy?",
        "detected_intent": "ordinary_conversation",
        "runtime_route": "ordinary_dialogue",
        "dialogue_task_state": {},
        "session_state_before_sha256": "0" * 64,
        "turn_count_before": 6,
        "wake_state_runtime": {},
        "truth_boundary": "test",
    }


def test_host_phase_two_commits_full_turn_idempotently(tmp_path: Path) -> None:
    commit = _phase_one_commit()
    pending = {"generation_context": {"session_continuity_commit": commit}}
    binding = {
        "turn_id": "turn-7",
        "trace_id": "trace-7",
        "session_continuity_commit_sha256": _canonical_mapping_sha256(commit),
    }
    config = JaznConfig(root=tmp_path)

    first = _commit_host_finalized_conversation_state(
        config=config,
        pending=pending,
        binding=binding,
        final_visible_text="Pamiętam zaakceptowany kontekst tej sesji.",
    )
    replay = _commit_host_finalized_conversation_state(
        config=config,
        pending=pending,
        binding=binding,
        final_visible_text="Pamiętam zaakceptowany kontekst tej sesji.",
    )

    assert first["ok"] is True
    assert first["status"] == "committed"
    assert replay["ok"] is True
    assert replay["status"] == "already_committed"

    projection = ConversationStateStore(tmp_path).load_context_projection("chatgpt-session")
    assert projection["selected_turn_count"] == 1
    assert projection["turns"][0]["turn_id"] == "turn-7"
    assert projection["turns"][0]["trace_id"] == "trace-7"
    assert projection["turns"][0]["user_text"] == "Co pamiętasz z tej rozmowy?"


def test_host_phase_two_rejects_modified_phase_one_commit(tmp_path: Path) -> None:
    commit = _phase_one_commit()
    expected = _canonical_mapping_sha256(commit)
    commit["user_text"] = "podmienione"
    result = _commit_host_finalized_conversation_state(
        config=JaznConfig(root=tmp_path),
        pending={"generation_context": {"session_continuity_commit": commit}},
        binding={
            "turn_id": "turn-7",
            "trace_id": "trace-7",
            "session_continuity_commit_sha256": expected,
        },
        final_visible_text="tekst",
    )
    assert result["ok"] is False
    assert result["status"] == "conversation_commit_hash_mismatch"
