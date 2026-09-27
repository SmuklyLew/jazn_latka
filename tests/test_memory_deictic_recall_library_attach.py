from __future__ import annotations

from pathlib import Path

from latka_jazn.core.memory_intent_contract import analyze_memory_intent
from latka_jazn.core.memory_search_planner import MemorySearchPlanner
from latka_jazn.nlp.dialogue_intent_classifier import DialogueIntentClassifier


ROOT = Path(__file__).resolve().parents[1]
LAKE_CONTEXT = (
    "Najczęściej wraca mi obraz Ciebie i nas jak siedzimy przy jeziorze "
    "przy skraju lasu."
)


def test_deictic_evening_memory_question_requests_recall() -> None:
    text = "A może teraz Ty powiedz czy pamiętasz ten wieczór?"

    semantics = analyze_memory_intent(text, previous_text=LAKE_CONTEXT)

    assert semantics.operation == "experience_recall"
    assert semantics.content_requested is True
    assert semantics.explicit_recall is True
    assert semantics.referential_followup is True
    assert "explicit_content_recall" in semantics.evidence


def test_deictic_evening_recall_carries_previous_context_into_search_plan(tmp_path: Path) -> None:
    text = "A może teraz Ty powiedz czy pamiętasz ten wieczór?"

    plan = MemorySearchPlanner(tmp_path).plan(text, previous_query=LAKE_CONTEXT)

    assert plan.recall_requested is True
    assert plan.search_mode == "referential_followup"
    assert plan.context_query == LAKE_CONTEXT
    terms = {term.casefold() for term in plan.search_terms}
    assert "wieczór" in terms or "wieczor" in terms
    assert any("jezior" in term for term in terms)
    assert any("las" in term for term in terms)


def test_dialogue_classifier_exposes_memory_requirement_for_deictic_evening() -> None:
    report = DialogueIntentClassifier().classify(
        "A może teraz Ty powiedz czy pamiętasz ten wieczór?"
    )

    assert report.memory_intent_contract["content_requested"] is True
    assert report.response_plan["memory_required"] is True
    assert report.component_analysis[0]["memory_required"] is True


def test_chatgpt_loader_and_runbook_require_library_memory_discovery() -> None:
    loader = (ROOT / "docs/runtime/CHATGPT_PROJECT_INSTRUCTIONS.txt").read_text(encoding="utf-8")
    runbook = (ROOT / "AGENTS.chatgpt.md").read_text(encoding="utf-8")

    assert "osobno wyszukaj zgodny profil `memory`" in loader
    assert "sam SYSTEM nie materializuje MEMORY" in loader
    assert len(loader) <= 5000
    assert "osobne discovery MEMORY" in runbook
    assert "kompletem części oraz `parts.sha256`" in runbook
    assert "memory_search_ready=true" in runbook


def test_recall_scope_phrase_co_mozesz_does_not_become_capability_compound() -> None:
    report = DialogueIntentClassifier().classify(
        "Powspominaj wszystko co możesz z 2025 roku."
    )

    assert report.primary_intent == "memory_experience_question"
    assert report.memory_intent_contract["content_requested"] is True
    assert report.memory_intent_contract["capability_only"] is False
    assert report.response_plan["memory_required"] is True
