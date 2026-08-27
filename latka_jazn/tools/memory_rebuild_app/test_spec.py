from __future__ import annotations

"""Single source of truth for Memory Rebuild Test00-04 and Final presentation.

The specs are descriptive contracts shared by Studio, CLI and protocol runners.
They deliberately distinguish *running* a protocol from the existing read-only
``test_profiles.py`` validators.
"""

from dataclasses import dataclass
from enum import Enum


class TestOutcome(str, Enum):
    NOT_RUN = "NOT RUN"
    PASSED = "PASSED"
    FAILED = "FAILED"
    LOSSY = "LOSSY"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True, slots=True)
class TestSpec:
    profile: str
    label: str
    goal: str
    inputs: tuple[str, ...]
    readiness: tuple[str, ...]
    phases: tuple[str, ...]
    checks: tuple[str, ...]
    outputs: tuple[str, ...]
    truth_boundary: tuple[str, ...]
    writes_test_artifacts: bool
    validator_profile: str | None = None


TEST_SPECS: tuple[TestSpec, ...] = (
    TestSpec(
        profile="test00",
        label="Test 00 — Source Fidelity / bezstratny odczyt",
        goal=(
            "Udowadnia, że wskazane źródła można odczytać w całości, zachować "
            "bajtowo oraz zinwentaryzować bez gubienia obserwowanych ról, typów "
            "treści i grafu rozmów."
        ),
        inputs=(
            "HTML/HTM, JSON lub ZIP eksportu",
            "opcjonalnie sidecary pełnego eksportu jako osobne źródła",
        ),
        readiness=(
            "źródło istnieje i jest zwykłym plikiem",
            "kodowanie/JSON są czytelne albo błąd jest jawnie raportowany",
            "ZIP przechodzi bezpieczną inspekcję ścieżek i CRC",
        ),
        phases=(
            "raw mirror",
            "pełny odczyt / parse",
            "inventory ról i content_type",
            "porównanie raw ↔ parsed",
            "round-trip SHA-256",
            "integrity report",
        ),
        checks=(
            "surowe bajty są zapisane do osobnej source-mirror SQLite",
            "SHA-256 BLOB po odczycie jest identyczny ze źródłem",
            "każdy obserwowany node/message ma odpowiednik po parsowaniu",
            "role user/assistant/system/tool oraz nieznane role są zachowywane, nie filtrowane",
            "content_type są zinwentaryzowane bez allowlistowego odrzucania",
            "parent/children, current path i branch points pozostają policzalne",
            "każdy członek ZIP jest odczytany do końca i ma SHA-256/CRC metadata",
            "rendered HTML fallback jest oznaczony LOSSY, nigdy PASSED",
            "Test00 nie tworzy L1/L2/L3 ani decyzji promocji",
        ),
        outputs=(
            "memory/rebuild_tests/test_00/<run-id>/source_mirror.sqlite3",
            "summary.private.json",
            "summary.sanitized.json",
        ),
        truth_boundary=(
            "PASSED dowodzi wierności odczytu i przechowania źródła, nie prawdziwości jego treści.",
            "Test00 nie oznacza wspomnienia, recall, aktywacji ani gotowości Jaźni.",
            "LOSSY oznacza, że źródło zachowano bajtowo, ale parser nie odtworzył pełnej struktury.",
        ),
        writes_test_artifacts=True,
        validator_profile=None,
    ),
    TestSpec(
        profile="test01",
        label="Test 01 — Kanoniczne, bezstratne L0",
        goal="Buduje izolowane, źródłowe L0 z materiałów zaakceptowanych przez Test00.",
        inputs=("zatwierdzony zestaw źródeł Test00", "manifest źródeł i ich SHA-256"),
        readiness=("Test00 bez FAILED/BLOCKED dla wymaganych źródeł", "jawna kolejność źródeł"),
        phases=("freeze inventory", "plan", "build L0", "verify provenance", "read-only validation"),
        checks=(
            "pełne grafy rozmów, branche i raw payload",
            "rewizje, assets, sidecary/embedded documents i dziennik mają proweniencję",
            "FTS5 i foreign keys są spójne",
            "brak automatycznej akceptacji doświadczeń oraz L2/L3",
        ),
        outputs=("izolowana memory_jazn.sqlite3", "manifest Test01", "raport walidacji"),
        truth_boundary=("L0 jest archiwum dowodowym, nie aktywną pamięcią autobiograficzną.",),
        writes_test_artifacts=True,
        validator_profile="test01",
    ),
    TestSpec(
        profile="test02",
        label="Test 02 — Normalizacja i projekcje",
        goal="Buduje i sprawdza wyłącznie pochodne widoki/klasyfikacje bez zmiany surowego L0.",
        inputs=("wynik Test01", "reguły normalizacji i indeksowania"),
        readiness=("zaliczona integralność Test01",),
        phases=("normalize", "classify", "index", "raw ↔ normalized reconciliation", "verify"),
        checks=(
            "visible/hidden/non-dialogue i role techniczne są rozdzielone",
            "memory eligibility i sensitivity są pochodnymi z dowodem źródłowym",
            "timestampy bez źródła nie są wymyślane",
            "FTS nie indeksuje rekordów wyłączonych przez safety gate",
            "raw source mirror i L0 pozostają byte/content-identical",
        ),
        outputs=("projekcje/indeksy Test02", "raport raw-normalized reconciliation"),
        truth_boundary=("Normalizacja nie promuje interpretacji do faktu ani wspomnienia.",),
        writes_test_artifacts=True,
        validator_profile="test02",
    ),
    TestSpec(
        profile="test03",
        label="Test 03 — Pełny rebuild integracyjny",
        goal="Wykonuje świeżą odbudowę jednej memory_jazn.sqlite3 i porównuje ją z wcześniejszymi etapami.",
        inputs=("zatwierdzone źródła", "wyniki Test00/01/02 jako immutable baseline"),
        readiness=("plan bez zapisu jest poprawny", "wszystkie wymagane źródła mają SHA-256"),
        phases=("dry-run", "fresh build", "dedupe/merge", "JSON↔HTML control", "reconciliation", "verify"),
        checks=(
            "identical/subset/extends/divergent są jawnie rozróżniane",
            "divergent nie powoduje utraty historycznej gałęzi",
            "manual HTML jest obsługiwany jako samodzielne źródło, gdy ma pełne jsonData",
            "porównanie używa stabilnych kluczy oraz hashy treści, nie samych liczników",
            "0 nierozwiązanych konfliktów wymagających decyzji operatora",
        ),
        outputs=("baseline Test03 memory_jazn.sqlite3", "manifest i reconciliation report"),
        truth_boundary=("Zielony rebuild nie dowodzi jeszcze jakości Recall ani naturalności rozmowy.",),
        writes_test_artifacts=True,
        validator_profile="test03",
    ),
    TestSpec(
        profile="test04",
        label="Test 04 — Prywatna akceptacja pełnej bazy",
        goal="Mierzy kompletność, reproducibility i Recall na rzeczywistych prywatnych danych.",
        inputs=("wszystkie znane źródła", "latest-export attestation", "prywatny benchmark Recall", "baseline Test03"),
        readiness=("zamrożony manifest źródeł", "przypadki Recall pozostają poza Git", "Test03 zaliczony"),
        phases=(
            "fresh build A",
            "same-target idempotence",
            "fresh build B",
            "reproducibility",
            "Test03 reconciliation",
            "Recall benchmark",
            "manual multi-turn",
            "optional restart continuity",
        ),
        checks=(
            "source completeness i exact provenance",
            "A==B dla semantycznego wyniku odbudowy",
            "Recall: direct/paraphrase/referential/temporal/update/conflict/negative/provenance",
            "abstention przy braku dowodu",
            "role/sensitive boundary bez wycieku credential/tool payload",
            "multi-turn używa właściwego źródła, nie zgaduje",
        ),
        outputs=("developer_test04_passed albo jawny zestaw blockerów", "sanitized metrics", "private evidence report"),
        truth_boundary=(
            "Test04 nie aktywuje pamięci i nie autoryzuje L2/L3.",
            "Syntetyczne CI nie zastępuje prywatnej akceptacji Recall.",
        ),
        writes_test_artifacts=True,
        validator_profile="test04",
    ),
    TestSpec(
        profile="final",
        label="Final — Freeze pełnej pamięci bazowej",
        goal="Zamraża zweryfikowaną bazę i dowody jako wejście do osobnego Verified Memory Restore.",
        inputs=("zaliczony Test04", "raporty Test00-04", "review/promotion ledgers"),
        readiness=("wszystkie blocking checks Test04 PASSED", "brak niejawnych automatycznych promocji"),
        phases=("SQLite Backup API snapshot", "full validation", "manifest sealing", "sanitized export"),
        checks=(
            "snapshot SQLite jest spójny",
            "private + sanitized manifests zgadzają się po hashach",
            "source manifest i database manifest są kompletne",
            "promotion ledger pozostaje fail-closed bez jawnej decyzji",
        ),
        outputs=("final memory_jazn.sqlite3", "database/source/test manifests", "candidate/review ledger"),
        truth_boundary=("Final jest gotowym wejściem do Verified Memory Restore, nie aktywną Jaźnią.",),
        writes_test_artifacts=True,
        validator_profile="final",
    ),
)

TEST_SPEC_BY_PROFILE = {item.profile: item for item in TEST_SPECS}
TEST_PROTOCOL_ORDER = tuple(item.profile for item in TEST_SPECS)


def get_test_spec(profile: str) -> TestSpec:
    try:
        return TEST_SPEC_BY_PROFILE[profile]
    except KeyError as exc:
        raise ValueError(f"unknown Memory Rebuild test protocol: {profile}") from exc


__all__ = [
    "TEST_PROTOCOL_ORDER",
    "TEST_SPECS",
    "TestOutcome",
    "TestSpec",
    "get_test_spec",
]
