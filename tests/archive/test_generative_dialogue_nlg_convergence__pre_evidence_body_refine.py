from __future__ import annotations

from types import SimpleNamespace

from latka_jazn.core.engine import _handler_body_can_cross_chatgpt_host_bridge
from latka_jazn.core.handlers.memory_experience_recall_handler import (
    MemoryExperienceRecallHandler,
)
from latka_jazn.core.runtime_answer_validator import RuntimeAnswerValidator
from latka_jazn.nlp.dialogue_intent_classifier import DialogueIntentClassifier


def _memory_handler_result():
    return MemoryExperienceRecallHandler().handle(
        "Co pamiętasz z naszych rozmów?",
        {
            "intent": "memory_experience_question",
            "memory_context": {
                "memory_recall_payload": {
                    "items": [
                        {
                            "item_id": "memory-1",
                            "content_excerpt": "Rozmawialiśmy o muzyce i ciszy.",
                            "source": "journal.sqlite3/journal_entries:memory-1",
                            "timestamp": "2025-08-08T00:12:21Z",
                            "confidence": 0.91,
                        }
                    ]
                }
            },
            "required_components": [],
        },
    )


def test_memory_recall_handler_exposes_evidence_for_language_realization() -> None:
    result = _memory_handler_result()

    assert result.data["requires_model_language_realization"] is True
    assert result.data["preserve_handler_body"] is False
    assert result.data["memory_evidence_role"] == "generation_context_not_visible_answer"
    assert result.memory_sources[0]["item_id"] == "memory-1"
    assert "Źródło:" not in result.body
    assert "surowych rekordów" in result.body


def test_chatgpt_host_bridge_cannot_pass_memory_evidence_body_directly() -> None:
    result = _memory_handler_result()
    accepted = _handler_body_can_cross_chatgpt_host_bridge(
        adapter_status={
            "adapter_id": "chatgpt_runtime_adapter",
            "provider": "chatgpt_host",
            "kind": "hosted_chatgpt_bridge",
        },
        handler_result=result,
        handler_missing=[],
        handler_required=[],
        handler_satisfied=set(),
        template_origin={},
        validation=SimpleNamespace(accepted=True),
    )

    assert accepted is False


def test_semantically_compound_turn_requires_every_component() -> None:
    validation = RuntimeAnswerValidator().validate(
        user_text="Co pamiętasz z naszych rozmów i co czujesz teraz?",
        body="Pamiętam nasze rozmowy i mam dla nich źródłowo uziemiony zapis.",
        route="memory_experience_recall",
        detected_intent="memory_experience_question",
    )

    assert validation.accepted is False
    assert validation.mismatch_reason == "compound_component_coverage_incomplete"
    ledger = validation.component_coverage_ledger
    assert ledger["coverage_required"] is True
    assert ledger["complete"] is False
    assert any(
        "self_affect" in record["missing_semantic_intents"]
        for record in ledger["records"]
    )


def test_nlp_nlg_capability_question_routes_to_system_diagnostic() -> None:
    report = DialogueIntentClassifier().classify(
        "Czy NLP działa i czy jest wystarczający dla twoich wypowiedzi?"
    )

    assert report.primary_intent == "system_diagnostic_question"
    assert report.diagnostic_request is True
    assert report.question_object == "language_architecture"
