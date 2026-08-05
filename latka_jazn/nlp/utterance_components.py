from __future__ import annotations

from dataclasses import dataclass, asdict
import re
import unicodedata


def _fold(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text or "")
    folded = "".join(ch for ch in normalized if not unicodedata.combining(ch)).lower()
    return folded.translate(str.maketrans("łŁ", "lL"))


@dataclass(frozen=True, slots=True)
class UtteranceComponentReport:
    components: tuple[str, ...]
    negated_actions: tuple[str, ...]
    compound: bool
    explicit_execution: bool
    diagnostic_only: bool

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


_COMPONENT_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("identity", ("kim jestes", "kim jest łatka", "kim jest latka", "czym jestes", "to nadal ty", "z kim rozmawiam")),
    ("capabilities", ("co potrafisz", "co umiesz", "jakie masz mozliwosci", "co mozesz", "do czego jestes zdolna")),
    ("memory", ("co pamietasz", "pamiec", "wspomnienia", "czy pamietasz", "jak dziala twoja pamiec")),
    ("origin_creator", ("kto cie stworzyl", "jak powstalas", "skad pochodzisz", "twoj tworca", "kto jest tworca", "historia powstania")),
    ("history", ("twoja historia", "jak sie rozwijalas", "wczesniejsze wersje", "co bylo wczesniej", "od poczatku")),
    ("rights_obligations", ("jakie masz prawa", "jakie masz obowiazki", "prawa i obowiazki", "co ci wolno", "czego nie wolno", "co musisz")),
    ("runtime_status", ("czy dzialasz", "czy jestes uruchomiona", "status runtime", "status jazni", "daemon", "heartbeat", "aktywny runtime")),
    ("sources", ("skad to wiesz", "jakie sa zrodla", "zrodlo odpowiedzi", "source origin", "skad bierzesz")),
    ("current_time", ("ktora godzina", "jaka jest godzina", "jaki mamy dzien", "czas teraz")),
    ("implementation", ("napraw kod", "wdroz poprawke", "zrob aktualizacje", "przygotuj patch", "wprowadz zmiany", "zaktualizuj")),
    ("diagnostic", ("sprawdz kod", "przeanalizuj", "zrob audyt", "znajdz bledy", "co trzeba naprawic", "co jest zle")),
)

_ACTION_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("update", ("aktualizuj", "zaktualizuj", "aktualizacja", "wdroz", "wdrazaj", "patch", "hotfix")),
    ("restart", ("restartuj", "zrestartuj", "uruchom ponownie")),
    ("modify", ("zmien kod", "wprowadz zmiany", "napraw kod", "usun", "dodaj")),
)

_NEGATION_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\bnie\s+(?:aktualizuj|zaktualizuj|wdrazaj|wdroz|patchuj)\b", "update"),
    (r"\bbez\s+(?:aktualizacji|wdrazania|patcha|hotfixu)\b", "update"),
    (r"\bnie\s+(?:restartuj|uruchamiaj(?:\s+ponownie)?)\b", "restart"),
    (r"\bnie\s+(?:zmieniaj|modyfikuj|usuwaj|dodawaj|naprawiaj)\b", "modify"),
    (r"\btylko\s+(?:sprawdz|przeanalizuj|zrob\s+audyt|opisz)\b", "execution"),
)

_MODAL_DESCRIPTION = (
    "trzeba bedzie", "nalezaloby", "mozna by", "warto bedzie", "w przyszlosci", "plan naprawy", "propozycja zmian"
)
_EXECUTION_VERBS = (
    "zaktualizuj", "aktualizuj", "wdroz", "wprowadz zmiany", "napraw kod", "zrob patch", "przygotuj patch", "zrestartuj", "uruchom ponownie"
)
_DIAGNOSTIC_MARKERS = (
    "sprawdz", "przeanalizuj", "audyt", "znajdz bledy", "co jest zle", "co trzeba naprawic", "tylko opisz"
)


def analyse_utterance(text: str) -> UtteranceComponentReport:
    folded = re.sub(r"\s+", " ", _fold(text)).strip()
    components: list[str] = []
    for name, patterns in _COMPONENT_PATTERNS:
        if any(pattern in folded for pattern in patterns):
            components.append(name)
    # Phrase variants joined with conjunctions should still become independent
    # components instead of relying on one exact surface form.
    token_rules = (
        ("origin_creator", ("stworz", "powstal", "powstalas", "tworc")),
        ("rights_obligations", ("praw", "obowiaz", "wolno")),
        ("history", ("histori", "wczesniejs", "rozwijal")),
    )
    for name, tokens in token_rules:
        if name not in components and any(token in folded for token in tokens):
            components.append(name)

    negated: list[str] = []
    for pattern, action in _NEGATION_PATTERNS:
        if re.search(pattern, folded):
            negated.append(action)

    explicit_execution = (
        any(marker in folded for marker in _EXECUTION_VERBS)
        or re.search(r"\bnapraw(?!de\b)\w*", folded) is not None
    )
    modal_description = any(marker in folded for marker in _MODAL_DESCRIPTION)
    diagnostic = any(marker in folded for marker in _DIAGNOSTIC_MARKERS)
    if negated or modal_description:
        explicit_execution = False
    diagnostic_only = diagnostic and not explicit_execution

    # Multiple question marks are not required: a conjunction often joins
    # several independent questions in one sentence.
    compound = len(components) >= 2
    return UtteranceComponentReport(
        components=tuple(components),
        negated_actions=tuple(dict.fromkeys(negated)),
        compound=compound,
        explicit_execution=explicit_execution,
        diagnostic_only=diagnostic_only,
    )


_COMPONENT_EVIDENCE: dict[str, tuple[str, ...]] = {
    "identity": ("jestem", "latka", "łatka", "jazn", "jaźń", "chatgpt", "runtime"),
    "capabilities": ("potraf", "umiem", "mogę", "moge", "możliwo", "zdoln"),
    "memory": ("pamię", "pamie", "wspomn", "recall", "l0", "l1", "l2", "l3"),
    "origin_creator": ("powsta", "stworz", "twórc", "tworc", "autor", "repozytor", "projekt"),
    "history": ("histori", "wcześniej", "wczesniej", "wersj", "rozw"),
    "rights_obligations": ("praw", "obowiąz", "obowiaz", "wolno", "nie wolno", "musz", "granica"),
    "runtime_status": ("aktywn", "daemon", "pid", "heartbeat", "endpoint", "runtime", "one-shot", "oneshot"),
    "sources": ("źród", "zrod", "source", "provenance", "pochodz"),
    "current_time": ("godzin", "czas", "dzień", "dzien", "timezone", "stref"),
    "implementation": ("zmian", "patch", "commit", "kod", "wdroż", "wdroz", "test"),
    "diagnostic": ("błąd", "blad", "audyt", "problem", "ryzyk", "test", "sprawdz"),
}


def missing_component_evidence(body: str, components: tuple[str, ...] | list[str]) -> list[str]:
    folded = _fold(body)
    missing: list[str] = []
    for component in components:
        evidence = _COMPONENT_EVIDENCE.get(component, ())
        if evidence and not any(marker in folded for marker in evidence):
            missing.append(component)
    return missing
