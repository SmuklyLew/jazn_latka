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


def test_phase_one_binds_verified_checkpoint_not_stale_daemon_session(tmp_path) -> None:
    from latka_jazn.config import JaznConfig
    from latka_jazn.core.chat_command_contract import _build_session_continuity_commit, _canonical_mapping_sha256
    from latka_jazn.core.runtime_session_state import RuntimeSessionState, RuntimeSessionStateStore

    stored = RuntimeSessionState.create(session_id="daemon-session", source_client="chatgpt")
    stored.update(user_text="Already finalized", visible_text="Accepted answer", intent="greeting", route="greeting")
    assert RuntimeSessionStateStore(tmp_path).save(stored, turn_count=7)["session_state_saved"]

    daemon_stale = RuntimeSessionState.create(session_id="daemon-session", source_client="chatgpt")
    result = {"session": daemon_stale.to_dict(), "session_provenance": {"continuity_turn_count": 0}}
    commit = _build_session_continuity_commit(
        result,
        user_text="Next user message",
        detected_intent="system_update_execution_request",
        runtime_route="runtime_diagnostic",
        config=JaznConfig(root=tmp_path),
    )
    assert commit["session_state_before_sha256"] == _canonical_mapping_sha256(stored.to_dict())
    assert commit["turn_count_before"] == 7
    assert RuntimeSessionStateStore(tmp_path).load_or_create(session_id="daemon-session").last_visible_text == "Accepted answer"
