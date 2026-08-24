from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from latka_jazn.core.memory_grounded_generation_bridge import (
    enforce_memory_grounding,
)
from latka_jazn.core.memory_recall_presenter import MemoryRecallPresenter
from latka_jazn.core.response_candidate import ResponseCandidate
from latka_jazn.core.response_candidate_evaluator import (
    evaluate_response_candidate,
    select_best_candidate,
)
from latka_jazn.core.response_candidate_generator import generate_response_candidates
from latka_jazn.memory.memory_recall_contract import MemoryRecallContractBuilder


def _candidate(
    text: str,
    *,
    source: str = "runtime_fallback",
    used_ids: list[str] | None = None,
) -> ResponseCandidate:
    return ResponseCandidate(
        candidate_id="candidate",
        text=text,
        source=source,
        provider="fixture",
        model="fixture",
        status="completed",
        used_memory_item_ids=used_ids or [],
        generation_reason="fixture",
    )


def test_contract_uses_the_frozen_presenter_payload_and_stable_item_id() -> None:
    context = {
        "counts": {"conversation_archive_hits": 1},
        "memory_recall_payload": {
            "items": [
                {
                    "item_type": "conversation_archive",
                    "content_excerpt": "Source-backed scene from June.",
                    "source": "archive/source-1",
                    "timestamp": "2025-06-15T12:00:00Z",
                    "confidence": 0.91,
                    "relevance_score": 0.88,
                    "grounding": "conversation_archive_v1+fts_v1",
                }
            ]
        },
        "conversation_archive_hits": [
            {"excerpt": "A different raw value must not replace the frozen payload."}
        ],
    }

    first = MemoryRecallContractBuilder().build(context, user_text="recall June")
    second = MemoryRecallContractBuilder().build(context, user_text="recall June")

    assert len(first.items) == 1
    assert first.items[0]["content"] == "Source-backed scene from June."
    assert first.items[0]["item_id"].startswith("memory_")
    assert first.items[0]["item_id"] == second.items[0]["item_id"]


class _Adapter:
    def describe(self) -> dict[str, Any]:
        return {"status": "configured", "name": "fixture", "model": "fixture"}

    def generate(self, _request: Any) -> Any:
        return SimpleNamespace(
            status="completed",
            text="I use the declared source.",
            provider="fixture",
            model="fixture",
            source_origin="model_adapter",
            endpoint_used="fixture://local",
            to_dict=lambda: {
                "status": "completed",
                "text": "I use the declared source.",
                "structured_output": {"used_memory_item_ids": ["memory_allowed"]},
            },
        )


def test_candidates_declare_only_memory_ids_the_generator_actually_received() -> None:
    candidates = generate_response_candidates(
        adapter=_Adapter(),
        nlg_plan={"detected_intent": "memory_experience_question", "route": "memory"},
        model_context={
            "user_message": "recall",
            "allowed_memory_items": [
                {"item_id": "memory_allowed", "excerpt": "scene", "source": "archive"}
            ],
        },
        fallback_body="Safe runtime fallback.",
    )

    assert candidates[0].used_memory_item_ids == []
    assert candidates[1].used_memory_item_ids == ["memory_allowed"]


def test_runtime_fallback_is_not_accepted_when_it_makes_an_unbacked_memory_claim() -> None:
    candidate = _candidate("Pamietam nieistniejace spotkanie.")
    grounding = enforce_memory_grounding(candidate, [])
    evaluation = evaluate_response_candidate(
        candidate=candidate,
        nlg_plan={"memory_policy": "required_grounded_payload"},
        model_context={"allowed_memory_items": []},
        response_policy={},
    )

    assert grounding.accepted is False
    assert "memory_claim_without_grounded_items" in grounding.violations
    assert evaluation.accepted is False
    selected = select_best_candidate([candidate], [evaluation])
    assert selected.candidate_id == "all_candidates_rejected_safe_fallback"
    assert selected.used_memory_item_ids == []


def test_honest_memory_denial_is_not_treated_as_a_positive_memory_claim() -> None:
    for text in (
        "Nie pamiętam tego.",
        "Nie przypominam sobie tamtej rozmowy.",
        "Nie mogę sobie przypomnieć tego szczegółu.",
        "Nie mam tego w mojej pamięci.",
    ):
        candidate = _candidate(text)
        grounding = enforce_memory_grounding(candidate, [])
        evaluation = evaluate_response_candidate(
            candidate=candidate,
            nlg_plan={"memory_policy": "required_grounded_payload"},
            model_context={"allowed_memory_items": []},
            response_policy={},
        )

        assert grounding.accepted is True, (text, grounding.violations)
        assert evaluation.accepted is True, (text, evaluation.violations)


def test_positive_claim_after_an_honest_denial_still_requires_grounding() -> None:
    candidate = _candidate("Nie pamiętam tamtego dnia, ale pamiętam naszą rozmowę.")

    grounding = enforce_memory_grounding(candidate, [])
    evaluation = evaluate_response_candidate(
        candidate=candidate,
        nlg_plan={"memory_policy": "required_grounded_payload"},
        model_context={"allowed_memory_items": []},
        response_policy={},
    )

    assert grounding.accepted is False
    assert "memory_claim_without_grounded_items" in grounding.violations
    assert evaluation.accepted is False


def test_presenter_rejects_current_turn_echo_and_explicitly_bad_source() -> None:
    user_text = "This exact current turn is not a historical memory."
    context = {
        "query_terms": ["historical"],
        "living_memory_hits": [
            {
                "content_excerpt": user_text,
                "source_layer": "journal",
                "source_database": "fixture",
                "source_locator": "echo",
                "truth_status": "source_recorded",
            },
            {
                "content_excerpt": "A quarantined historical scene.",
                "source_layer": "journal",
                "source_database": "fixture",
                "source_locator": "bad",
                "truth_status": "quarantined",
            },
            {
                "content_excerpt": "A distinct, accepted historical scene with useful detail.",
                "source_layer": "journal",
                "source_database": "fixture",
                "source_locator": "good",
                "truth_status": "source_recorded",
                "confidence": 0.9,
            },
        ],
    }

    payload = MemoryRecallPresenter().build_payload(context, user_text=user_text)

    assert len(payload["items"]) == 1
    assert payload["items"][0]["source"].endswith("good")
