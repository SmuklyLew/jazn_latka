from __future__ import annotations

from latka_jazn.core.model_context_compiler import compile_model_context


def _plan() -> dict:
    return {
        "answer_kind": "natural_dialogue",
        "detected_intent": "ordinary_conversation",
        "route": "ordinary_dialogue",
        "memory_policy": "not_needed",
        "source_policy": "runtime_only",
        "forbidden_components": [],
        "truth_boundary": "runtime truth",
    }


def test_model_context_carries_bounded_durable_conversation_projection() -> None:
    history = {
        "schema_version": "conversation_context_projection/v1",
        "session_id": "session-a",
        "turns": [
            {
                "turn_id": "turn-1",
                "trace_id": "trace-1",
                "user_text": "Pamiętaj kontekst tej sesji.",
                "assistant_text": "Kontekst bieżącej sesji został przyjęty.",
                "accepted_at_utc": "2026-09-12T16:00:00+00:00",
                "source": "runtime",
            }
        ],
        "total_turn_count": 4,
        "selected_turn_count": 1,
        "omitted_turn_count": 3,
        "compaction_mode": "bounded_non_destructive_projection",
        "source_of_truth": "workspace_runtime/conversation_state per-turn accepted records",
        "projection_sha256": "a" * 64,
    }
    packet = compile_model_context(
        user_text="Co powiedziałem wcześniej?",
        cognitive_frame={"client_context": {"conversation_history": history}},
        nlg_plan=_plan(),
        thought_frame={"truth_boundary": "runtime truth"},
        response_policy={},
    ).to_dict()

    projection = packet["conversation_history"]
    assert projection["total_turn_count"] == 4
    assert projection["selected_turn_count"] == 1
    assert projection["omitted_turn_count"] == 3
    assert projection["turns"][0]["turn_id"] == "turn-1"
    assert "Pamiętaj kontekst" in projection["turns"][0]["user_text"]
    assert "conversation_history" in " ".join(packet["output_instructions"])


def test_model_context_history_is_sanitized_and_bounded() -> None:
    turns = [
        {
            "turn_id": f"turn-{index}",
            "trace_id": f"trace-{index}",
            "user_text": "u" * 1800,
            "assistant_text": "a" * 2400,
            "source": "runtime",
        }
        for index in range(10)
    ]
    packet = compile_model_context(
        user_text="dalej",
        cognitive_frame={
            "client_context": {
                "conversation_history": {
                    "turns": turns,
                    "total_turn_count": 10,
                }
            }
        },
        nlg_plan=_plan(),
        thought_frame={},
        response_policy={},
    ).to_dict()

    projection = packet["conversation_history"]
    assert projection["selected_turn_count"] < 10
    assert projection["omitted_turn_count"] > 0
    assert sum(
        len(turn["user_text"]) + len(turn["assistant_text"])
        for turn in projection["turns"]
    ) <= 10000
