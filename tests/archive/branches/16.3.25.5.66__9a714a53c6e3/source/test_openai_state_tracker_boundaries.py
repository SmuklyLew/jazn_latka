from __future__ import annotations

from pathlib import Path
import json

from latka_jazn.model_adapters.openai_state_tracker import OpenAIStateTracker


def test_invalid_dynamic_identifier_fields_are_not_replayed(tmp_path: Path) -> None:
    tracker = OpenAIStateTracker(tmp_path)
    tracker.path.write_text(
        json.dumps(
            {
                "session-1": {
                    "previous_response_id": ["not", "an", "identifier"],
                    "last_response_id": 7,
                    "conversation_id": {"invalid": True},
                    "updated_at_utc": False,
                    "store_policy": True,
                }
            }
        ),
        encoding="utf-8",
    )

    state = tracker.load("session-1")

    assert state.previous_response_id is None
    assert state.last_response_id is None
    assert state.conversation_id is None
    assert state.updated_at_utc is None
    assert state.store_policy is True
