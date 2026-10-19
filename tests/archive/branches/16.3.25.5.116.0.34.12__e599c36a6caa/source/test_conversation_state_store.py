from __future__ import annotations

import json
from pathlib import Path

from latka_jazn.core.conversation_state_store import ConversationStateStore


def test_finalized_turn_commit_is_idempotent_and_hash_bound(tmp_path: Path) -> None:
    store = ConversationStateStore(tmp_path)
    first = store.append_finalized_turn(
        session_id="session-a",
        turn_id="turn-1",
        trace_id="trace-1",
        user_text="Cześć",
        assistant_text="Hej!",
        source="test",
    )
    replay = store.append_finalized_turn(
        session_id="session-a",
        turn_id="turn-1",
        trace_id="trace-1",
        user_text="Cześć",
        assistant_text="Hej!",
        source="test",
    )

    assert first["ok"] is True
    assert first["status"] == "committed"
    assert replay["ok"] is True
    assert replay["status"] == "already_committed"
    assert replay["idempotent"] is True

    payload = json.loads(Path(first["path"]).read_text(encoding="utf-8"))
    assert payload["session_id"] == "session-a"
    assert payload["turn_id"] == "turn-1"
    assert payload["trace_id"] == "trace-1"
    assert len(payload["record_sha256"]) == 64


def test_same_turn_with_different_visible_text_fails_closed(tmp_path: Path) -> None:
    store = ConversationStateStore(tmp_path)
    assert store.append_finalized_turn(
        session_id="session-a",
        turn_id="turn-1",
        trace_id="trace-1",
        user_text="Pytanie",
        assistant_text="Odpowiedź A",
        source="test",
    )["ok"] is True

    conflict = store.append_finalized_turn(
        session_id="session-a",
        turn_id="turn-1",
        trace_id="trace-1",
        user_text="Pytanie",
        assistant_text="Odpowiedź B",
        source="test",
    )

    assert conflict["ok"] is False
    assert conflict["status"] == "turn_commit_conflict"


def test_bounded_projection_keeps_all_accepted_turns_on_disk(tmp_path: Path) -> None:
    store = ConversationStateStore(tmp_path)
    for index in range(100):
        result = store.append_finalized_turn(
            session_id="long-session",
            turn_id=f"turn-{index:03d}",
            trace_id=f"trace-{index:03d}",
            user_text=f"user-{index}-" + ("u" * 80),
            assistant_text=f"assistant-{index}-" + ("a" * 100),
            source="synthetic-long-conversation",
        )
        assert result["ok"] is True

    projection = store.load_context_projection(
        "long-session",
        max_turns=12,
        max_chars=2200,
    )

    assert projection["total_turn_count"] == 100
    assert 1 <= projection["selected_turn_count"] <= 12
    assert projection["omitted_turn_count"] == 100 - projection["selected_turn_count"]
    assert projection["selected_chars"] <= 2200
    assert projection["compaction_mode"] == "bounded_non_destructive_projection"
    assert projection["turns"][-1]["turn_id"] == "turn-099"

    session_dir = store._session_dir("long-session")
    assert len(list(session_dir.glob("*.json"))) == 100
