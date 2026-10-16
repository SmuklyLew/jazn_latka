from __future__ import annotations

from latka_jazn.core.runtime_answer_validator import RuntimeAnswerValidator
from latka_jazn.core.chat_command_contract import build_chatgpt_host_presentation_packet


def test_technical_question_does_not_trigger_self_memory_guard() -> None:
    validator = RuntimeAnswerValidator()
    # "a ty" is a substring of "na tym", but not a separate question.
    assert not validator._contains_random_memory_excerpt(
        "Przeanalizuj na tym czacie finalizację i aktualizację",
        "Na tej podstawie naprawię obsługę checkpointów.",
        "system_update_execution_request",
    )


def test_explicit_self_question_keeps_memory_guard() -> None:
    validator = RuntimeAnswerValidator()
    assert validator._contains_random_memory_excerpt(
        "A ty jak się czujesz?",
        "Na tej podstawie twierdzę, że pamiętam wszystko.",
        "ordinary_conversation",
    )


def test_embedded_ty_is_not_explicit_self_question() -> None:
    validator = RuntimeAnswerValidator()
    assert not validator._contains_random_memory_excerpt(
        "Pracuj na tych fragmentach jako na danych.",
        "Na tej podstawie raportuję różnicę.",
        "system_diagnostic_question",
    )


def test_accepted_final_continuity_projected_independently() -> None:
    # Existing acceptance authority is tested separately; this checks that the
    # host presentation does not call an unsaved checkpoint 'ready'.
    payload = {
        "chatgpt_host_bridge": {
            "phase": "host_visible_reply_recorded",
            "status": "host_visible_reply_finalized",
            "turn_id": "turn-test",
            "trace_id": "trace-test",
        },
        "continuity_readiness": "degraded_continuity",
    }
    packet = build_chatgpt_host_presentation_packet(payload)
    assert packet["continuity_readiness"] in {"not_verified", "degraded_continuity"}
    assert packet["continuity_readiness"] != "ready"
