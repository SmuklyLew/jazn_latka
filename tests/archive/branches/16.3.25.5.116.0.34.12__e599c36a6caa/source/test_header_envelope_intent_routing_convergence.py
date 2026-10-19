from __future__ import annotations

import pytest

from latka_jazn.core.chat_command_contract import (
    build_chatgpt_host_presentation_packet,
    chatgpt_result_has_displayable_host_final,
)
from latka_jazn.core.host_visible_finalization import sha256_host_visible_text
from latka_jazn.nlp.dialogue_intent_classifier import DialogueIntentClassifier


HEADER = "🕒 2026-09-29 02:00:42"
FINAL = f"{HEADER}\n🛠️ Łatka\n\nTreść po poprawnej finalizacji."


@pytest.mark.parametrize(
    "text",
    [
        "Przepraszam, ale w twojej wiadomości nie było już nagłówka (jaki czas, kto pisze).",
        "Możesz od razu sprawdzić dlaczego nagłówek zniknął i jak to naprawić.",
        "Timestamp zniknął z odpowiedzi.",
        "Brakuje nagłówka w kolejnej wiadomości.",
    ],
)
def test_header_loss_is_runtime_diagnostic_not_practical_repair(text: str) -> None:
    report = DialogueIntentClassifier().classify(text)

    assert report.primary_intent == "runtime_behavior_diagnostic_request"
    assert report.question_object == "runtime_header_continuity"
    assert report.diagnostic_request is True
    assert report.primary_intent != "practical_repair_advice"


@pytest.mark.parametrize(
    "text",
    [
        "Jak naprawić zawór, bo kapie?",
        "Jak naprawić kran, który kapie?",
        "Jak wyciąć otwór w kafelku?",
    ],
)
def test_physical_repair_still_routes_to_practical_advice(text: str) -> None:
    report = DialogueIntentClassifier().classify(text)

    assert report.primary_intent == "practical_repair_advice"


def test_generic_system_repair_is_never_stolen_by_practical_route() -> None:
    report = DialogueIntentClassifier().classify("Jak naprawić system Jaźni?")

    assert report.primary_intent != "practical_repair_advice"
    assert report.question_object != "practical"


def _phase2_payload(
    *,
    include_envelope_verdict: bool = True,
    include_consumption: bool = True,
    include_capture_hash: bool = True,
) -> dict[str, object]:
    digest = sha256_host_visible_text(FINAL)
    capture: dict[str, object] = {
        "turn_id": "turn-header-1",
        "trace_id": "trace-header-1",
        "timestamp_header": HEADER,
        "state_emoticon": "🛠️",
        "author_label": "Łatka",
        "author_source": "jazn_runtime",
        "final_visible_text": FINAL,
    }
    if include_capture_hash:
        capture["final_text_sha256"] = digest
    if include_envelope_verdict:
        capture["envelope_present_in_final"] = True

    payload: dict[str, object] = {
        "final_visible_text": FINAL,
        "chatgpt_host_bridge": {
            "phase": "host_visible_reply_recorded",
            "turn_id": "turn-header-1",
            "trace_id": "trace-header-1",
            "timestamp_header": HEADER,
            "state_emoticon": "🛠️",
            "author_label": "Łatka",
            "author_source": "jazn_runtime",
            "user_text_sha256": "b" * 64,
        },
        "host_visible_finalization": {
            "accepted": True,
            "final_visible_text": FINAL,
            "final_text_sha256": digest,
            "turn_id": "turn-header-1",
            "trace_id": "trace-header-1",
        },
        "host_visible_reply_capture": capture,
    }
    if include_consumption:
        payload["host_request_consumption"] = {
            "state": "consumed",
            "turn_id": "turn-header-1",
            "trace_id": "trace-header-1",
        }
    return payload


def test_display_exact_requires_affirmative_envelope_evidence() -> None:
    payload = _phase2_payload(include_envelope_verdict=False)

    assert chatgpt_result_has_displayable_host_final(payload) is False
    presentation = build_chatgpt_host_presentation_packet(payload)
    assert presentation["action"] == "host_diagnostic"
    assert presentation["accepted_visible_turn_ready"] is False


def test_display_exact_requires_capture_hash() -> None:
    payload = _phase2_payload(include_capture_hash=False)

    assert chatgpt_result_has_displayable_host_final(payload) is False


def test_display_exact_requires_consumed_host_request() -> None:
    payload = _phase2_payload(include_consumption=False)

    assert chatgpt_result_has_displayable_host_final(payload) is False
    presentation = build_chatgpt_host_presentation_packet(payload)
    assert presentation["action"] == "host_diagnostic"
    assert presentation["final_visible_text"] == ""


def test_complete_envelope_and_settlement_are_displayable() -> None:
    payload = _phase2_payload()

    assert chatgpt_result_has_displayable_host_final(payload) is True
    presentation = build_chatgpt_host_presentation_packet(payload)
    assert presentation["action"] == "display_exact"
    assert presentation["accepted_visible_turn_ready"] is True
    assert presentation["final_visible_text"].startswith(
        f"{HEADER}\n🛠️ Łatka\n\n"
    )


def test_diagnostic_downgrade_clears_all_visible_readiness_flags() -> None:
    payload = _phase2_payload()
    bridge = payload["chatgpt_host_bridge"]
    assert isinstance(bridge, dict)
    bridge.pop("user_text_sha256")

    presentation = build_chatgpt_host_presentation_packet(payload)

    assert presentation["action"] == "host_diagnostic"
    assert presentation["phase"] == "host_diagnostic_required"
    assert presentation["accepted_visible_turn_ready"] is False
    assert presentation["visible_turn_readiness"] == "not_ready"
    assert presentation["must_display_exactly"] is False
    assert presentation["must_not_paraphrase"] is False
    assert presentation["must_not_claim_runtime_voice"] is True
    assert presentation["must_not_claim_latka_voice"] is True
    assert presentation["must_preserve_runtime_voice"] is False
    assert presentation["must_preserve_latka_voice"] is False
    assert presentation["required_visible_prefix"] is None
    assert presentation["final_visible_text"] == ""
    assert presentation["final_text_sha256"] is None
