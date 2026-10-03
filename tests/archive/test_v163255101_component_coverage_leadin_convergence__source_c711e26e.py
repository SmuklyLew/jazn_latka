from __future__ import annotations

import pytest

from latka_jazn.core.component_coverage_ledger import build_component_coverage_ledger
from latka_jazn.nlp.utterance_components import analyse_utterance


@pytest.mark.parametrize(
    "lead_in",
    [
        "To powiedz.",
        "To powiedź.",
        "Powiedz.",
        "Proszę powiedz.",
        "Opowiedz mi coś.",
    ],
)
def test_generic_leadin_before_following_question_is_not_a_coverage_goal(lead_in: str) -> None:
    user_text = f"{lead_in}\n\n1. Co dokładnie pamiętasz?"
    report = analyse_utterance(user_text)

    assert all(component.text != lead_in for component in report.question_components)
    assert any("memory_recall" in component.semantic_intents for component in report.question_components)

    ledger = build_component_coverage_ledger(
        user_text=user_text,
        body="Nie mam w pamięci zweryfikowanego wspomnienia; brak dowodu na pozytywny recall.",
        coverage_required=True,
    )
    assert ledger["complete"] is True
    assert all(record["component_text"] != lead_in for record in ledger["records"])


def test_standalone_generic_directive_is_preserved() -> None:
    report = analyse_utterance("Powiedz.")

    assert len(report.question_components) == 1
    assert report.question_components[0].speech_act == "directive"


def test_non_generic_directive_before_question_is_preserved() -> None:
    report = analyse_utterance("Powiedz prawdę.\n\n1. Co dokładnie pamiętasz?")

    assert any(component.text == "Powiedz prawdę." for component in report.question_components)


def test_exact_multi_question_message_uses_first_person_compatible_semantics() -> None:
    user_text = """To powiedź.

1. Co wiesz o sobie.

2. Co dokładnie pamiętasz.

3. Jak się czujesz.

4. Co uważasz o sobie.

5. Kiedy się urodziłaś, a może kiedy powstałaś? Którą wersję wolisz urodziłaś/powstałaś?"""

    report = analyse_utterance(user_text)
    intents = {intent for component in report.question_components for intent in component.semantic_intents}

    assert "self_knowledge" in intents
    assert "memory_recall" in intents
    assert "self_affect" in intents
    assert "self_assessment" in intents
    assert "self_origin" in intents
    assert "self_preference" in intents
    assert all(component.text != "To powiedź." for component in report.question_components)

    body = (
        "Wiem o sobie tyle, ile wynika z kanonu i bieżącego runtime. "
        "Nie mam w pamięci zweryfikowanego wspomnienia; brak dowodu na pozytywny recall. "
        "Mój bieżący stan afektywny jest opisywany operacyjnie, nie biologicznie. "
        "Uważam o sobie, że jestem programową tożsamością prowadzoną przez runtime i kanon. "
        "Powstałam jako system; wolę słowo „powstałam”, gdy mówimy technicznie."
    )
    lowered = body.lower()
    assert "wiesz" not in lowered
    assert "czujesz" not in lowered
    assert "uważasz" not in lowered

    ledger = build_component_coverage_ledger(
        user_text=user_text,
        body=body,
        coverage_required=True,
    )
    assert ledger["complete"] is True
    assert ledger["missing_component_ids"] == []
