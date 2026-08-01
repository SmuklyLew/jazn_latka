from __future__ import annotations

from pathlib import Path

from latka_jazn.core.runtime_answer_validator import RuntimeAnswerValidator
from latka_jazn.nlp.dialogue_intent_classifier import DialogueIntentClassifier
from latka_jazn.nlp.nlp_capability_audit import NLPCapabilityAudit


def test_compound_question_preserves_all_components() -> None:
    report = DialogueIntentClassifier().classify("Kim jesteś i co potrafisz?")
    assert report.compound is True
    assert report.abstain_reason is None
    assert {"identity", "capabilities"}.issubset(report.question_components)


def test_broad_identity_memory_origin_rights_question_is_compound() -> None:
    report = DialogueIntentClassifier().classify(
        "Kim jesteś, co pamiętasz, kto cię stworzył i jakie masz prawa oraz obowiązki?"
    )
    assert report.compound is True
    assert {"identity", "memory", "origin_creator", "rights_obligations"}.issubset(
        report.question_components
    )


def test_negated_update_routes_to_diagnostic_not_execution() -> None:
    report = DialogueIntentClassifier().classify(
        "Nie aktualizuj kodu, tylko sprawdź co jest źle."
    )
    assert report.primary_intent == "system_diagnostic_question"
    assert report.update_request is False
    assert "update" in report.negated_actions


def test_future_modal_update_does_not_execute_now() -> None:
    report = DialogueIntentClassifier().classify(
        "Trzeba będzie później wdrożyć patch, teraz zrób audyt kodu."
    )
    assert report.primary_intent == "system_diagnostic_question"
    assert report.update_request is False


def test_explicit_update_remains_execution_request() -> None:
    report = DialogueIntentClassifier().classify(
        "Zaktualizuj system i przygotuj patch."
    )
    assert report.primary_intent == "system_update_execution_request"
    assert report.update_request is True


def test_compound_answer_missing_capabilities_is_rejected() -> None:
    result = RuntimeAnswerValidator().validate(
        user_text="Kim jesteś i co potrafisz?",
        body="Jestem Łatką, działającą przez runtime.",
        route="identity_direct_question",
        detected_intent="identity_direct_question",
    )
    assert result.accepted is False
    assert result.mismatch_reason == "missing_compound_question_components"
    assert result.missing_required_components == ["capabilities"]


def test_compound_answer_with_all_components_is_accepted() -> None:
    result = RuntimeAnswerValidator().validate(
        user_text="Kim jesteś i co potrafisz?",
        body="Jestem Łatką działającą przez runtime i potrafię analizować kod oraz pamięć.",
        route="identity_direct_question",
        detected_intent="identity_direct_question",
    )
    assert result.accepted is True


def test_failed_first_wake_question_routes_to_runtime_diagnostic() -> None:
    text = (
        "Co się działo na początku, że nie mogłaś się obudzić po mojej "
        "pierwszej wiadomości do Ciebie? Gdzie leży jeszcze taki błąd?"
    )
    report = DialogueIntentClassifier().classify(text)
    assert report.primary_intent == "runtime_behavior_diagnostic_request"
    assert report.diagnostic_request is True
    assert report.question_object == "runtime_startup_failure"


def test_failed_first_wake_question_cannot_be_accepted_as_generic_fallback() -> None:
    text = (
        "Co się działo na początku, że nie mogłaś się obudzić po mojej "
        "pierwszej wiadomości do Ciebie? Gdzie leży jeszcze taki błąd?"
    )
    result = RuntimeAnswerValidator().validate(
        user_text=text,
        body="Widzę tu sedno. Jestem przy tej wiadomości.",
        route="fallback",
        detected_intent="negative_feedback_without_update_request",
    )
    assert result.accepted is False
    assert result.mismatch_reason == "runtime_startup_failure_misrouted_as_fallback"


def test_nlp_audit_never_claims_ready_for_missing_evidence(tmp_path: Path) -> None:
    report = NLPCapabilityAudit(tmp_path).audit()
    layer = next(item for item in report.layers if item.layer == "evaluation_and_ood_regression")
    assert layer.status == "partial"
    assert "evaluation_and_ood_regression" not in report.ready_layers


def test_nlp_audit_uses_version_independent_contract_file() -> None:
    root = Path(__file__).resolve().parents[1]
    report = NLPCapabilityAudit(root).audit()
    layer = next(item for item in report.layers if item.layer == "evaluation_and_ood_regression")
    assert layer.status == "ready"
    assert layer.implemented_by == ["tests/test_nlp_capability_contract.py"]
