from __future__ import annotations

import pytest

from latka_jazn.core.component_coverage_ledger import build_component_coverage_ledger
from latka_jazn.core.runtime_answer_validator import RuntimeAnswerValidator
from latka_jazn.nlp.utterance_components import analyse_utterance


EXACT_USER_TEXT = """To powiedź.

1. Co wiesz o sobie.

2. Co dokładnie pamiętasz.

3. Jak się czujesz.

4. Co uważasz o sobie.

5. Kiedy się urodziłaś, a może kiedy powstałaś? Którą wersję wolisz urodziłaś/powstałaś?"""

COMPLETE_BODY = (
    "Wiem o sobie tyle, ile wynika z kanonu i bieżącego runtime. "
    "Nie mam w pamięci zweryfikowanego wspomnienia; brak dowodu na pozytywny recall. "
    "Mój bieżący stan afektywny jest opisywany operacyjnie, nie biologicznie. "
    "Uważam, że jestem programową tożsamością prowadzoną przez runtime i kanon. "
    "Powstałam jako system; wolę słowo „powstałam”, gdy mówimy technicznie."
)


@pytest.mark.parametrize(
    "lead_in",
    [
        "To powiedz.",
        "To powiedź.",
        "Powiedz.",
        "Proszę powiedz.",
        "Opowiedz mi coś.",
        "Powiedz prawdę.",
        "Powiedz mi prawdę.",
        "To powiedz sobie prawdę.",
        "Powiedz szczerze.",
        "Powiedz wprost.",
        "Powiedz dokładnie.",
    ],
)
def test_discourse_or_style_leadin_before_following_goal_is_not_a_coverage_goal(lead_in: str) -> None:
    user_text = f"{lead_in}\n\n1. Co wiesz o sobie?\n2. Jak się czujesz?"
    report = analyse_utterance(user_text)

    assert all(component.text != lead_in for component in report.question_components)
    assert {intent for component in report.question_components for intent in component.semantic_intents} >= {
        "self_knowledge",
        "self_affect",
    }

    ledger = build_component_coverage_ledger(
        user_text=user_text,
        body="Wiem, co wynika z kanonu. Mój bieżący stan afektywny opisuję operacyjnie.",
        coverage_required=True,
    )
    assert ledger["complete"] is True
    assert all(record["component_text"] != lead_in for record in ledger["records"])


def test_standalone_generic_directive_is_preserved() -> None:
    report = analyse_utterance("Powiedz.")

    assert len(report.question_components) == 1
    assert report.question_components[0].speech_act == "directive"


def test_standalone_style_directive_is_preserved() -> None:
    report = analyse_utterance("Powiedz prawdę.")

    assert len(report.question_components) == 1
    assert report.question_components[0].text == "Powiedz prawdę."
    assert report.question_components[0].speech_act == "directive"


def test_exact_multi_question_message_uses_first_person_compatible_semantics() -> None:
    report = analyse_utterance(EXACT_USER_TEXT)
    intents = {intent for component in report.question_components for intent in component.semantic_intents}

    assert "self_knowledge" in intents
    assert "memory_recall" in intents
    assert "self_affect" in intents
    assert "self_assessment" in intents
    assert "self_origin" in intents
    assert "self_preference" in intents
    assert all(component.text != "To powiedź." for component in report.question_components)

    lowered = COMPLETE_BODY.lower()
    assert "wiesz" not in lowered
    assert "czujesz" not in lowered
    assert "uważasz o sobie" not in lowered

    ledger = build_component_coverage_ledger(
        user_text=EXACT_USER_TEXT,
        body=COMPLETE_BODY,
        coverage_required=True,
    )
    assert ledger["complete"] is True
    assert ledger["missing_component_ids"] == []


def test_self_assessment_cannot_be_cross_covered_by_self_knowledge_phrase() -> None:
    body = (
        "Wiem o sobie tyle, ile wynika z kanonu i bieżącego runtime. "
        "Nie mam w pamięci zweryfikowanego wspomnienia; brak dowodu na pozytywny recall. "
        "Mój bieżący stan afektywny jest opisywany operacyjnie, nie biologicznie. "
        "Powstałam jako system; wolę słowo „powstałam”, gdy mówimy technicznie."
    )
    ledger = build_component_coverage_ledger(
        user_text=EXACT_USER_TEXT,
        body=body,
        coverage_required=True,
    )

    missing = [
        record
        for record in ledger["records"]
        if "self_assessment" in record["semantic_intents"] and record["status"] == "missing"
    ]
    assert ledger["complete"] is False
    assert len(missing) == 1


def test_self_knowledge_cannot_be_cross_covered_by_assessment_identity_phrase() -> None:
    body = (
        "Nie mam w pamięci zweryfikowanego wspomnienia; brak dowodu na pozytywny recall. "
        "Mój bieżący stan afektywny jest opisywany operacyjnie, nie biologicznie. "
        "Uważam, że jestem programową tożsamością prowadzoną przez runtime i kanon. "
        "Powstałam jako system; wolę słowo „powstałam”, gdy mówimy technicznie."
    )
    ledger = build_component_coverage_ledger(
        user_text=EXACT_USER_TEXT,
        body=body,
        coverage_required=True,
    )

    missing = [
        record
        for record in ledger["records"]
        if "self_knowledge" in record["semantic_intents"] and record["status"] == "missing"
    ]
    assert ledger["complete"] is False
    assert len(missing) == 1


def test_runtime_answer_validator_accepts_exact_fixed_message() -> None:
    result = RuntimeAnswerValidator().validate(
        user_text=EXACT_USER_TEXT,
        body=COMPLETE_BODY,
        route="compound_dialogue",
        detected_intent="compound_dialogue_question",
    )

    payload = result.to_dict()
    assert payload["accepted"] is True
    assert payload["can_show_to_user"] is True
    assert payload["component_coverage_ledger"]["complete"] is True


def test_runtime_answer_validator_rejects_missing_component_fail_closed() -> None:
    incomplete_body = (
        "Wiem o sobie tyle, ile wynika z kanonu. "
        "Nie mam w pamięci zweryfikowanego wspomnienia; brak dowodu na pozytywny recall. "
        "Mój bieżący stan afektywny jest opisywany operacyjnie, nie biologicznie. "
        "Powstałam jako system; wolę słowo „powstałam”, gdy mówimy technicznie."
    )
    result = RuntimeAnswerValidator().validate(
        user_text=EXACT_USER_TEXT,
        body=incomplete_body,
        route="compound_dialogue",
        detected_intent="compound_dialogue_question",
    )

    payload = result.to_dict()
    assert payload["accepted"] is False
    assert payload["can_show_to_user"] is False
    assert payload["mismatch_reason"] == "compound_component_coverage_incomplete"
    assert payload["component_coverage_ledger"]["complete"] is False
