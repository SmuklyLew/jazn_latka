from __future__ import annotations

from pathlib import Path

from latka_jazn.core.conversation_state_store import ConversationStateStore


def test_conversation_state_survives_store_recreation(tmp_path: Path) -> None:
    first_process = ConversationStateStore(tmp_path)
    for index in range(3):
        committed = first_process.append_finalized_turn(
            session_id="restart-session",
            turn_id=f"turn-{index}",
            trace_id=f"trace-{index}",
            user_text=f"user-{index}",
            assistant_text=f"assistant-{index}",
            source="restart-test",
        )
        assert committed["ok"] is True

    # Recreate the store as a new process/session owner would after restart.
    after_restart = ConversationStateStore(tmp_path)
    projection = after_restart.load_context_projection(
        "restart-session",
        max_turns=10,
        max_chars=10_000,
    )

    assert projection["total_turn_count"] == 3
    assert projection["selected_turn_count"] == 3
    assert [turn["turn_id"] for turn in projection["turns"]] == [
        "turn-0",
        "turn-1",
        "turn-2",
    ]
    assert projection["turns"][-1]["assistant_text"] == "assistant-2"
