from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from latka_jazn.core.memory_intent_contract import (
    analyze_memory_intent,
    intent_requires_memory_content,
    parse_temporal_scope,
    strip_temporal_language,
)
from latka_jazn.core.memory_search_planner import MemorySearchPlanner
from latka_jazn.nlp.dialogue_intent_classifier import DialogueIntentClassifier


NOW = datetime(2026, 8, 24, 12, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    "text",
    [
        "Powspominaj wszystko co możesz z 2025 roku.",
        "Co pamiętasz z 2025?",
        "Przypomnij sobie nasze rozmowy z czerwca.",
        "Co wspominasz z zeszłego roku?",
        "Co pamiętałaś z czerwca 2025?",
        "Co przypominasz sobie z 2025 roku?",
    ],
)
def test_polish_memory_forms_request_content(text: str) -> None:
    semantics = analyze_memory_intent(text, now=NOW)

    assert semantics.operation == "experience_recall"
    assert semantics.content_requested is True
    assert semantics.capability_only is False


@pytest.mark.parametrize(
    "text",
    [
        "Czy potrafisz pamiętać nasze rozmowy?",
        "Czy pamiętasz?",
    ],
)
def test_memory_capability_question_does_not_request_content(text: str) -> None:
    semantics = analyze_memory_intent(text, now=NOW)

    assert semantics.operation == "capability"
    assert semantics.capability_only is True
    assert semantics.content_requested is False


def test_polite_request_with_concrete_scope_is_content_recall() -> None:
    semantics = analyze_memory_intent(
        "Czy możesz sobie przypomnieć nasze rozmowy z czerwca?",
        now=NOW,
    )

    assert semantics.operation == "experience_recall"
    assert semantics.content_requested is True
    assert semantics.capability_only is False


def test_store_directive_is_not_recall() -> None:
    semantics = analyze_memory_intent("Pamiętaj, że jutro wracamy do projektu.", now=NOW)

    assert semantics.operation == "store_directive"
    assert semantics.content_requested is False


def test_negated_store_form_is_forget_not_store() -> None:
    semantics = analyze_memory_intent(
        "Nie pamiętaj, że jutro wracamy do projektu.",
        now=NOW,
    )

    assert semantics.operation == "forget_directive"
    assert semantics.negated_recall is True
    assert semantics.content_requested is False
    assert "forget_directive" in semantics.evidence


def test_negated_recall_is_fail_closed_but_positive_contrast_wins() -> None:
    blocked = analyze_memory_intent("Nie wspominaj 2025 roku.", now=NOW)
    selected = analyze_memory_intent(
        "Nie wspominaj 2024, tylko przypomnij 2025.",
        now=NOW,
    )

    assert blocked.content_requested is False
    assert blocked.negated_recall is True
    assert selected.content_requested is True
    assert selected.temporal_scope is not None
    assert selected.temporal_scope.start_utc == "2024-12-31T23:00:00Z"
    assert selected.temporal_scope.end_utc_exclusive == "2025-12-31T23:00:00Z"


def test_calendar_year_uses_warsaw_boundaries() -> None:
    scope = parse_temporal_scope("Powspominaj 2025 rok.", now=NOW)

    assert scope is not None
    assert scope.precision == "year"
    assert scope.start_utc == "2024-12-31T23:00:00Z"
    assert scope.end_utc_exclusive == "2025-12-31T23:00:00Z"


def test_relative_year_and_implicit_month_are_deterministic() -> None:
    last_year = parse_temporal_scope("z zeszłego roku", now=NOW)
    june = parse_temporal_scope("z czerwca", now=NOW)

    assert last_year is not None
    assert last_year.start_utc == "2024-12-31T23:00:00Z"
    assert last_year.end_utc_exclusive == "2025-12-31T23:00:00Z"
    assert june is not None
    assert june.start_utc == "2026-05-31T22:00:00Z"
    assert june.end_utc_exclusive == "2026-06-30T22:00:00Z"


@pytest.mark.parametrize(
    ("text", "expected_month"),
    [
        ("w styczniu", 1),
        ("z lutego", 2),
        ("w marcu", 3),
        ("z kwietnia", 4),
        ("do maja", 5),
        ("w czerwcu", 6),
        ("z lipca", 7),
        ("w sierpniu", 8),
        ("we wrześniu", 9),
        ("w październiku", 10),
        ("z listopada", 11),
        ("w grudniu", 12),
    ],
)
def test_explicit_polish_month_forms_are_parsed(text: str, expected_month: int) -> None:
    scope = parse_temporal_scope(text, now=NOW)

    assert scope is not None
    assert scope.precision == "month"
    start_local = datetime.fromtimestamp(scope.start_epoch, tz=timezone.utc).astimezone(
        ZoneInfo("Europe/Warsaw")
    )
    assert start_local.month == expected_month


@pytest.mark.parametrize(
    "text",
    [
        "czerwony samochód",
        "marzenia o domu",
        "oni mają naprawić moduł",
    ],
)
def test_non_calendar_words_do_not_create_month_scope(text: str) -> None:
    assert parse_temporal_scope(text, now=NOW) is None


def test_year_scope_stripping_preserves_non_calendar_words() -> None:
    text = "czerwony samochód z 2025 roku"
    scope = parse_temporal_scope(text, now=NOW)

    assert scope is not None
    assert scope.precision == "year"
    assert strip_temporal_language(text, scope) == "czerwony samochód z"


def test_month_range_is_half_open_and_cross_year_range_anchors_end_year() -> None:
    summer = parse_temporal_scope("od czerwca do sierpnia 2025", now=NOW)
    winter = parse_temporal_scope("od listopada do lutego 2025", now=NOW)

    assert summer is not None
    assert summer.precision == "month_range"
    assert summer.start_utc == "2025-05-31T22:00:00Z"
    assert summer.end_utc_exclusive == "2025-08-31T22:00:00Z"
    assert winter is not None
    assert winter.start_utc == "2024-10-31T23:00:00Z"
    assert winter.end_utc_exclusive == "2025-02-28T23:00:00Z"


def test_correction_uses_positive_month_and_inherits_previous_year() -> None:
    semantics = analyze_memory_intent(
        "Nie, to było w lipcu, nie w czerwcu.",
        previous_text="Przypomnij sobie nasze rozmowy z czerwca 2025.",
        now=NOW,
    )

    assert semantics.correction is True
    assert semantics.content_requested is True
    assert semantics.temporal_scope is not None
    assert semantics.temporal_scope.start_utc == "2025-06-30T22:00:00Z"
    assert semantics.temporal_scope.end_utc_exclusive == "2025-07-31T22:00:00Z"


def test_referential_followup_inherits_previous_temporal_scope() -> None:
    semantics = analyze_memory_intent(
        "A co wtedy czułaś?",
        previous_text="Powspominaj 2025 rok.",
        now=NOW,
    )

    assert semantics.referential_followup is True
    assert semantics.content_requested is True
    assert semantics.temporal_scope is not None
    assert semantics.temporal_scope.start_utc == "2024-12-31T23:00:00Z"


@pytest.mark.parametrize(
    "text",
    [
        "Poszukaj tego wspomnienia.",
        "Chcę odnaleźć najwcześniejsze wspólne wspomnienie.",
    ],
)
def test_memory_search_phrases_are_content_recall(text: str) -> None:
    semantics = analyze_memory_intent(text, now=NOW)

    assert semantics.operation == "experience_recall"
    assert semantics.content_requested is True


@pytest.mark.parametrize(
    "text",
    [
        "Powspominaj wszystko co możesz z 2025 roku.",
        "Co pamiętasz z 2025?",
        "Przypomnij sobie nasze rozmowy z czerwca.",
        "Co wspominasz z zeszłego roku?",
    ],
)
def test_temporal_only_plan_does_not_require_year_or_month_in_fts(
    tmp_path: Path,
    text: str,
) -> None:
    plan = MemorySearchPlanner(tmp_path).plan(
        text,
        fallback_terms=["2025", "czerwca", "roku"],
        now=NOW,
    )

    assert plan.schema_version == "memory_search_planner/v2"
    assert plan.recall_requested is True
    assert plan.search_mode == "temporal_period"
    assert plan.search_terms == []
    assert plan.temporal_scope
    assert plan.memory_intent_contract["content_requested"] is True
    temporal_pass = next(
        item for item in plan.search_passes if item["name"] == "temporal_conversation_archive"
    )
    assert temporal_pass["enabled"] is True
    assert temporal_pass["terms"] == []


def test_temporal_semantic_plan_keeps_topic_but_removes_calendar_tokens(tmp_path: Path) -> None:
    plan = MemorySearchPlanner(tmp_path).plan(
        "Przypomnij spotkanie przy Katedrze z czerwca 2025.",
        now=NOW,
    )
    normalized_terms = {term.casefold() for term in plan.search_terms}

    assert plan.search_mode == "temporal_semantic_query"
    assert "2025" not in normalized_terms
    assert not any("czerw" in term for term in normalized_terms)
    assert any("spotkan" in term for term in normalized_terms)
    assert any("katedr" in term for term in normalized_terms)


def test_referential_plan_preserves_original_memory_query_and_scope(tmp_path: Path) -> None:
    plan = MemorySearchPlanner(tmp_path).plan(
        "A co wtedy czułaś?",
        previous_query="Powspominaj 2025 rok.",
        now=NOW,
    )

    assert plan.search_mode == "referential_followup"
    assert plan.context_query == "Powspominaj 2025 rok."
    assert plan.temporal_scope["start_utc"] == "2024-12-31T23:00:00Z"
    assert "2025" not in {term.casefold() for term in plan.search_terms}


def test_correction_plan_preserves_memory_anchor_and_uses_corrected_month(tmp_path: Path) -> None:
    plan = MemorySearchPlanner(tmp_path).plan(
        "Nie, to było w lipcu, nie w czerwcu.",
        previous_query="Przypomnij sobie nasze rozmowy z czerwca 2025.",
        now=NOW,
    )

    assert plan.search_mode == "referential_followup"
    assert plan.context_query == "Przypomnij sobie nasze rozmowy z czerwca 2025."
    assert plan.temporal_scope["start_utc"] == "2025-06-30T22:00:00Z"
    assert plan.temporal_scope["end_utc_exclusive"] == "2025-07-31T22:00:00Z"
    assert "2025" not in {term.casefold() for term in plan.search_terms}
    assert not any("czerw" in term or "lip" in term for term in plan.search_terms)


def test_canonical_memory_content_intents_include_active_runtime_names() -> None:
    assert intent_requires_memory_content("self_memory_recall_request") is True
    assert intent_requires_memory_content("memory_experience_question") is True
    assert intent_requires_memory_content("user_memory_recall_request") is True
    assert intent_requires_memory_content("capability_status_question") is False


def test_negated_recall_clause_does_not_hide_explicit_system_execution() -> None:
    report = DialogueIntentClassifier().classify(
        "Nie wspominaj teraz; napraw moduł pamięci."
    )

    assert report.primary_intent == "system_update_execution_request"
    assert report.update_request is True
    assert report.memory_intent_contract["negated_recall"] is True


def test_recall_and_system_execution_keep_execution_primary_and_recall_secondary() -> None:
    report = DialogueIntentClassifier().classify(
        "Przypomnij sobie 2025 rok i napraw moduł temporal recall."
    )

    assert report.primary_intent == "system_update_execution_request"
    assert "memory_experience_question" in report.secondary_intents
    assert report.update_request is True
    assert report.memory_intent_contract["content_requested"] is True


def test_negated_system_execution_is_not_revived_by_memory_compound() -> None:
    report = DialogueIntentClassifier().classify(
        "Przypomnij sobie 2025 rok, ale nie naprawiaj modułu temporal recall."
    )

    assert report.primary_intent == "memory_experience_question"
    assert report.update_request is False
    assert report.memory_intent_contract["content_requested"] is True
