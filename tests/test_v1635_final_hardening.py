from __future__ import annotations

from pathlib import Path

from latka_jazn.core.component_coverage_ledger import build_component_coverage_ledger
from latka_jazn.core.handlers.compound_dialogue_handler import CompoundDialogueHandler
from latka_jazn.core.memory_recall_presenter import MemoryRecallItem, MemoryRecallPresenter
from latka_jazn.core.memory_slot_selector import MemorySlotSelector
from latka_jazn.core.route_contract_matrix import RouteContractMatrix
from latka_jazn.core.runtime_answer_validator import RuntimeAnswerValidator
from latka_jazn.nlp.dialogue_intent_classifier import DialogueIntentClassifier
from latka_jazn.version import PACKAGE_RELEASE_NAME, PACKAGE_VERSION


BRANCH_RELEASE = "persistent-runtime-e2e-hardening"


def _item(
    content: str,
    *,
    item_type: str,
    source_type: str,
    role: str = "",
    kind: str = "",
    source: str = "synthetic",
    timestamp: str | None = "2025-08-16T16:00:00+02:00",
    confidence: float | None = 0.9,
    provenance: str = "pamiętam",
) -> MemoryRecallItem:
    return MemoryRecallItem(
        item_type=item_type,
        query_term=None,
        timestamp=timestamp,
        source=source,
        confidence=confidence,
        grounding="v1635_test",
        relevance_score=0.9,
        relevance_label="wysoka",
        meaning_assessment="synthetic evidence",
        content_excerpt=content,
        semantic_source_type=source_type,
        truth_status="source_recorded",
        provenance_label=provenance,
        metadata={"author_role": role, "kind": kind},
    )


def test_release_identity_tracks_current_successor_hardening() -> None:
    assert PACKAGE_VERSION == "16.3.6"
    assert PACKAGE_RELEASE_NAME == BRANCH_RELEASE


def test_canonical_route_lexicon_covers_new_dialogue_families() -> None:
    matrix = RouteContractMatrix()
    assert matrix.classify("Co najbardziej lubisz?").primary_intent == "self_preference_question"
    assert matrix.classify("Skąd się wzięłaś jako Łatka i jak powstałaś?").primary_intent == "self_origin_question"
    assert matrix.classify("Jak często zastanawiasz się nad swoją przeszłością?").primary_intent == "self_introspection_question"
    assert matrix.classify("Co pamiętasz z naszych rozmów?").primary_intent == "memory_recall_request"
    assert matrix.classify("Skąd wiesz, że naprawdę to pamiętasz?").primary_intent == "memory_provenance_question"


def test_capability_vs_recall_is_explicit_in_canonical_lexicon() -> None:
    matrix = RouteContractMatrix()
    capability = matrix.classify("Czy potrafisz pamiętać dawne rozmowy?")
    recall = matrix.classify("Co pamiętasz z dawnych rozmów?")
    assert capability.primary_intent == "memory_capability_question"
    assert recall.primary_intent == "memory_recall_request"
    assert capability.primary_intent != recall.primary_intent


def test_contextual_czego_brakuje_distinguishes_system_gap_from_evidence_gap() -> None:
    matrix = RouteContractMatrix()
    system_gap = matrix.classify("Czego brakuje w tym module pamięci?")
    evidence_gap = matrix.classify("Czego brakuje do potwierdzenia tego wspomnienia?")
    assert system_gap.primary_intent == "system_capability_gap_question"
    assert evidence_gap.primary_intent == "memory_evidence_gap_question"
    assert evidence_gap.primary_intent != "system_capability_gap_question"


def test_compound_handler_exposes_boolean_coverage_contract_and_component_ids() -> None:
    text = "Jaki jest twój ulubiony kolor? Kiedy się urodziłaś?"
    report = DialogueIntentClassifier().classify(text)
    assert report.primary_intent == "compound_dialogue_question"
    result = CompoundDialogueHandler().handle(
        text,
        {
            "intent": report.primary_intent,
            "dialogue_intent_report": report.to_dict(),
            "memory_context": {"memory_gate": {"allow_memory_content": True}},
        },
    )
    assert result.data["coverage_required"] is True
    ids = result.data["required_component_ids"]
    assert len(ids) == len(report.component_analysis)
    assert ids
    assert len(ids) == len(set(ids))


def test_component_coverage_ledger_blocks_partial_compound_answer() -> None:
    user_text = "Jaki jest twój ulubiony kolor? Kiedy się urodziłaś?"
    body = "Moją preferencją jest zielony i ten kolor lubię najbardziej."
    ledger = build_component_coverage_ledger(
        user_text=user_text,
        body=body,
        coverage_required=True,
    )
    assert ledger["complete"] is False
    assert len(ledger["required_component_ids"]) == 2
    assert len(ledger["missing_component_ids"]) == 1

    validation = RuntimeAnswerValidator().validate(
        user_text=user_text,
        body=body,
        route="compound_dialogue",
        detected_intent="compound_dialogue_question",
    )
    assert validation.accepted is False
    assert validation.mismatch_reason == "compound_component_coverage_incomplete"
    assert validation.component_coverage_ledger["complete"] is False


def test_component_coverage_ledger_accepts_every_component_or_explicit_gap() -> None:
    user_text = "Jaki jest twój ulubiony kolor? Kiedy się urodziłaś?"
    body = (
        "Moją preferencją jest zielony; ten kolor lubię najbardziej. "
        "Jeśli pytasz o mój początek, nie jest to biologiczne urodzenie: "
        "powstałam jako system, a źródłem tej warstwy jest kanon."
    )
    validation = RuntimeAnswerValidator().validate(
        user_text=user_text,
        body=body,
        route="compound_dialogue",
        detected_intent="compound_dialogue_question",
    )
    assert validation.accepted is True
    assert validation.component_coverage_ledger["complete"] is True
    assert {record["status"] for record in validation.component_coverage_ledger["records"]} <= {
        "covered", "evidence_gap"
    }


def test_memory_slot_selector_uses_distinct_semantic_evidence_records() -> None:
    items = [
        _item(
            "Podczas pobytu w Görlitz pojechaliśmy do kamieniołomów.",
            item_type="episode",
            source_type="active_memory",
            kind="event",
            source="memory_jazn.sqlite3:event",
        ),
        _item(
            "Powiedziałeś: jedziemy do kamieniołomów około szesnastej.",
            item_type="conversation_archive",
            source_type="conversation_archive",
            role="user",
            source="conversation_archive:user",
            provenance="odzyskano z archiwum",
        ),
        _item(
            "Odpowiedziałam, że zapamiętam ten wspólny wyjazd.",
            item_type="conversation_archive",
            source_type="conversation_archive",
            role="assistant",
            source="conversation_archive:assistant",
            provenance="odzyskano z archiwum",
        ),
        _item(
            "Później w refleksji myślałam o tym wyjeździe jako o ważnym wspólnym doświadczeniu.",
            item_type="journal_entry",
            source_type="journal_reflection",
            role="assistant",
            kind="reflection",
            source="journal:reflection",
        ),
    ]
    plan = MemorySlotSelector().build_slot_plan(
        items,
        requested_slots=(
            "event_fact", "user_utterance", "latka_utterance", "later_reflection",
            "time_context", "source", "truth_status", "confidence", "evidence_gap",
        ),
    )
    slots = plan["slots"]
    semantic = ["event_fact", "user_utterance", "latka_utterance", "later_reflection"]
    assert all(slots[name]["status"] == "supported" for name in semantic)
    evidence_ids = [slots[name]["evidence_id"] for name in semantic]
    assert len(evidence_ids) == len(set(evidence_ids)) == 4
    assert "Görlitz" in slots["event_fact"]["value"]
    assert "Powiedziałeś" in slots["user_utterance"]["value"]
    assert "Odpowiedziałam" in slots["latka_utterance"]["value"]
    assert "refleksji" in slots["later_reflection"]["value"]
    assert slots["time_context"]["derived_from_slot"] == "event_fact"
    assert slots["source"]["derived_from_slot"] == "event_fact"


def test_memory_slot_selector_fails_closed_when_reflection_is_missing() -> None:
    items = [
        _item(
            "Podczas pobytu w Görlitz pojechaliśmy do kamieniołomów.",
            item_type="episode",
            source_type="active_memory",
            kind="event",
        ),
        _item(
            "Powiedziałeś, że jedziemy około szesnastej.",
            item_type="conversation_archive",
            source_type="conversation_archive",
            role="user",
        ),
    ]
    plan = MemorySlotSelector().build_slot_plan(
        items,
        requested_slots=("event_fact", "user_utterance", "later_reflection", "evidence_gap"),
    )
    assert plan["slots"]["event_fact"]["status"] == "supported"
    assert plan["slots"]["user_utterance"]["status"] == "supported"
    assert plan["slots"]["later_reflection"]["status"] == "evidence_gap"
    assert plan["slots"]["evidence_gap"]["status"] == "supported"
    assert "later_reflection" in plan["slots"]["evidence_gap"]["value"]


def test_presenter_delegates_slot_plan_to_semantic_selector() -> None:
    presenter = MemoryRecallPresenter()
    items = [
        _item(
            "Powiedziałeś, że wyjazd do kamieniołomów był ważny.",
            item_type="conversation_archive",
            source_type="conversation_archive",
            role="user",
        ),
        _item(
            "Odpowiedziałam, że też tak go zapamiętam.",
            item_type="conversation_archive",
            source_type="conversation_archive",
            role="assistant",
        ),
    ]
    plan = presenter.build_slot_plan(
        items,
        user_text="Co powiedziałem ja i co odpowiedziałaś ty?",
    )
    assert plan["schema_version"] == "memory_recall_slot_plan/v2"
    assert plan["slots"]["user_utterance"]["evidence_id"] != plan["slots"]["latka_utterance"]["evidence_id"]


def test_v1635_files_are_not_private_memory_payloads() -> None:
    # This regression protects the branch hardening layer from accidentally
    # coupling its code contract to private memory databases.
    root = Path(__file__).resolve().parents[1]
    assert not (root / "memory_jazn.sqlite3").exists()
