from __future__ import annotations

from latka_jazn.nlp.dialogue_intent_classifier import DialogueIntentClassifier


REPORT_ONLY = """
Podsumowanie badań nad systemem Jaźni i planowaną aktualizacją. Najważniejszy wniosek
jest taki, że ClientError może powstawać przed uruchomieniem kodu, a raport opisuje
hipotezę związaną z transferem dużych plików MEMORY. Wnioski obejmują oddzielenie
SYSTEM od MEMORY, raportowanie postępu bootstrapu, walidację ZIP, live readiness,
diagnostykę snapshot status oraz routing intencji. Raport zawiera źródła OpenAI,
obserwacje, rekomendacje, hipotezy, plan implementacji i plan testów. Kolejna część
opisuje architekturę aktualizacji, możliwy patch, wersję systemu, manifest, ZIP,
moduły runtime, host ChatGPT oraz zachowanie finalizatora. To materiał analityczny:
przedstawia dowody, ograniczenia, potencjalne błędy, zalecenia i scenariusze testowe.
Wniosek końcowy mówi, że aktualizacja powinna używać mierzalnych etapów zamiast
sztucznego 99 procent. Raport nie wydaje polecenia modyfikacji repozytorium ani
wykonania patcha; opisuje jedynie wyniki badania i możliwe kierunki dalszych zmian.
Dodatkowe obserwacje dotyczą źródeł, telemetrii, recovery, pamięci opcjonalnej,
postępu rozpakowywania oraz zgodności hosta z systemem Jaźni i aktualną wersją.
"""


EXPLICIT_UPDATE = (
    "Na podstawie tych badań przygotuj update, pracuj na nowym branchu, "
    "popraw błędy logiczne i wdroż aktualizację systemu Jaźni."
)


def test_long_research_report_does_not_open_mutating_update_route() -> None:
    report = DialogueIntentClassifier().classify(REPORT_ONLY)

    assert report.primary_intent != "system_update_execution_request"
    assert report.update_request is False
    assert any(
        "report_material_cannot_open_mutating_update_route" in item
        for item in report.evidence
    )


def test_explicit_update_request_still_opens_mutating_route() -> None:
    report = DialogueIntentClassifier().classify(EXPLICIT_UPDATE)

    assert report.primary_intent == "system_update_execution_request"
    assert report.update_request is True
    assert report.question_object == "system_update"


def test_release_candidate_continuation_remains_update_execution() -> None:
    report = DialogueIntentClassifier().classify(
        "Sprawdź też kod źródłowy i pracuj dalej aż aktualizacja będzie "
        "pełnym release candidate gotowym do scalenia."
    )

    assert report.primary_intent == "system_update_execution_request"
    assert report.update_request is True
