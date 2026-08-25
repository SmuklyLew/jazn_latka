from __future__ import annotations

from dataclasses import asdict, dataclass
import re
import unicodedata
from typing import Any


def _fold(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text or "")
    folded = "".join(ch for ch in normalized if not unicodedata.combining(ch)).lower()
    return folded.translate(str.maketrans("łŁ", "lL"))


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip(" \t\r\n,;:")


@dataclass(frozen=True, slots=True)
class QuestionComponent:
    component_id: str
    text: str
    speech_act: str
    object_type: str
    semantic_intents: tuple[str, ...]
    memory_required: bool
    required_source_types: tuple[str, ...]
    requested_slots: tuple[str, ...]
    evidence: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class UtteranceComponentReport:
    # Backwards-compatible high-level labels used by the existing validator.
    components: tuple[str, ...]
    negated_actions: tuple[str, ...]
    compound: bool
    explicit_execution: bool
    diagnostic_only: bool
    # v16.3.4: meaningful clauses/questions with per-component semantics.
    question_components: tuple[QuestionComponent, ...] = ()
    semantic_intents: tuple[str, ...] = ()
    required_source_types: tuple[str, ...] = ()
    response_slots: tuple[str, ...] = ()
    capability_only: bool = False
    system_capability_gap: bool = False

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


_COMPONENT_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("identity", ("kim jestes", "kim jest łatka", "kim jest latka", "czym jestes", "to nadal ty", "z kim rozmawiam", "ta sama latka")),
    ("capabilities", ("co potrafisz", "co umiesz", "jakie masz mozliwosci", "co mozesz", "do czego jestes zdolna", "czy potrafisz")),
    ("memory", ("co pamietasz", "pamiec", "wspomnienia", "czy pamietasz", "jak dziala twoja pamiec", "przypomnij", "przywolaj")),
    ("preference", ("ulubiony", "najbardziej lubisz", "lubisz", "wolisz", "wybierasz", "co ci sie podoba", "preferenc")),
    ("origin_creator", ("kto cie stworzyl", "jak powstalas", "skad pochodzisz", "twoj tworca", "kto jest tworca", "historia powstania", "urodzilas")),
    ("introspection", ("zastanawialas sie", "refleksj", "nad swoja przeszloscia", "nad przeszloscia", "co o tym myslalas", "co pozniej o tym myslalas")),
    ("history", ("twoja historia", "jak sie rozwijalas", "wczesniejsze wersje", "co bylo wczesniej", "od poczatku", "swojej historii")),
    ("provenance", ("skad to wiesz", "skad wiesz", "jakie sa zrodla", "zrodlo odpowiedzi", "source origin", "zaznacz ich zrodlo", "z kanonu", "z pamieci", "wnioskujesz")),
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

# Clauses that are semantically coupled to a preceding question are deliberately
# retained as one component. We split only at strong sentence/question boundaries,
# then at a small set of unmistakable multi-question conjunctions.
_STRONG_SPLIT = re.compile(
    r"(?<=[?])\s+|(?<=[!.])\s+(?=(?:czy|co|jak|jaki|jaka|jakie|kiedy|dlaczego|czemu|skad|które|ktore|ile|czego|kto|[A-ZĄĆĘŁŃÓŚŹŻ0-9])\b)",
    re.IGNORECASE,
)
_INTERROGATIVE_START = re.compile(
    r"^(?:czy|co|jak|jaki|jaka|jakie|kiedy|dlaczego|czemu|skad|które|ktore|ile|czego|kto)\b",
    re.IGNORECASE,
)


def _split_meaningful_components(text: str) -> list[str]:
    raw = _clean(text)
    if not raw:
        return []
    parts: list[str] = []
    for sentence in _STRONG_SPLIT.split(raw):
        sentence = _clean(sentence)
        if not sentence:
            continue
        # Multiple '?' in one punctuation-less copy or clauses like
        # "... i co konkretnie pamiętasz" are independent only when the right
        # side starts with an interrogative phrase.
        chunks = re.split(
            r"\s+(?:i|oraz|a)\s+(?=(?:czy|co|jak|jaki|jaka|jakie|kiedy|dlaczego|skad|które|ktore|czego|kto)\b)",
            sentence,
            flags=re.IGNORECASE,
        )
        for chunk in chunks:
            chunk = _clean(chunk)
            if chunk:
                parts.append(chunk)
    return parts


def _contains_any(folded: str, markers: tuple[str, ...] | list[str]) -> bool:
    return any(marker in folded for marker in markers)


def _component_semantics(text: str, index: int) -> QuestionComponent:
    folded = _fold(text)
    intents: list[str] = []
    sources: list[str] = []
    slots: list[str] = []
    evidence: list[str] = []

    def add_intent(name: str, marker: str) -> None:
        if name not in intents:
            intents.append(name)
        evidence.append(marker)

    preference = _contains_any(folded, ("ulubion", "najbardziej lubisz", "lubisz", "wolisz", "wybierasz", "podoba", "preferenc"))
    origin = _contains_any(folded, ("urodzil", "powstalas", "powstanie", "skad pochodz", "kto cie stworz", "tworca"))
    introspection = _contains_any(folded, ("zastanawialas", "refleksj", "przeszlosc", "co pozniej o tym myslalas", "co o tym myslalas"))
    provenance = _contains_any(folded, ("skad wiesz", "skad to wiesz", "zrodlo", "provenance", "z kanonu", "z pamieci", "wnioskuj", "naprawde ja pamietasz"))
    identity_continuity = _contains_any(folded, ("ta sama latka", "ta sama latka", "nadal jestes", "ciaglos", "tozsamos"))
    architecture = bool(
        re.search(r"\bjak\s+dziala\b.*\bpamiec\b", folded)
        or re.search(r"\b(?:implementac|architektur|modul|gateway|runtime_write)\w*\b.*\bpamiec\w*\b", folded)
        or re.search(r"\bpamiec\w*\b.*\b(?:implementac|architektur|modul|gateway|runtime_write)\w*\b", folded)
        or _contains_any(folded, ("pamiec po odbudowie", "architektura pamieci", "warstwy pamieci", "runtime_write", "gateway pamieci"))
    )
    recall_directive = bool(
        re.search(r"\b(?:przypomnij|przywolaj|odtworz|odnajdz|poszukaj)\b", folded)
        or re.search(r"\b(?:co|jakie|ktore)\b.*\b(?:pamietasz|wspominasz)\b", folded)
        or _contains_any(folded, ("co konkretnie pamietasz", "dwie konkretne sytuacje", "dwa konkretne przyklady", "dwa przyklady"))
    )
    recall_context = _contains_any(folded, ("dawne rozmowy", "naszych rozmow", "z naszych rozmow", "pobyt", "wyjazd", "ksiazce", "muzyce"))
    recall = recall_directive or (recall_context and _contains_any(folded, ("pamiet", "wspomin", "odzyskuj")))
    capability = bool(
        re.search(r"\b(?:czy\s+)?(?:potrafisz|umiesz|mozesz|jestes w stanie)\b", folded)
        and _contains_any(folded, ("pamiet", "wspomin", "przypomin"))
    )
    evidence_gap = _contains_any(
        folded,
        ("czego brakuje do potwierdzenia", "brak dowodu", "nie masz w pamieci", "pamiec nie daje", "nie zgaduj", "czego nie masz w pamieci"),
    )
    technical_gap = bool(
        _contains_any(folded, ("czego brakuje", "czego nie ma", "co jest niepelne"))
        and _contains_any(folded, ("modul", "kod", "funkcj", "runtime", "system", "implementac", "api", "klasa", "repozytor"))
    )

    if preference:
        add_intent("self_preference", "preference_semantics")
        slots.extend(("preference_value", "preference_reason", "preference_provenance"))
        sources.extend(("conversation_archive", "active_memory", "journal_reflection", "canon", "current_state", "inference"))
    if origin:
        add_intent("self_origin", "origin_semantics")
        slots.extend(("origin_layer", "origin_time_or_boundary", "origin_provenance"))
        sources.extend(("canon", "conversation_archive", "active_memory", "technical_runtime", "inference"))
    if introspection:
        add_intent("self_introspection", "introspection_semantics")
        slots.extend(("reflection_content", "reflection_time", "reflection_provenance"))
        sources.extend(("journal_reflection", "conversation_archive", "active_memory", "canon", "inference"))
    if identity_continuity:
        add_intent("identity_continuity", "identity_continuity_semantics")
        slots.extend(("continuity_canon", "continuity_memory", "continuity_gap"))
        sources.extend(("canon", "conversation_archive", "active_memory", "journal_reflection", "inference"))
    if architecture:
        add_intent("memory_architecture", "memory_architecture_semantics")
        slots.extend(("architecture_status", "architecture_sources"))
        sources.extend(("technical_runtime", "source_code", "documentation", "runtime_status"))
    if capability:
        add_intent("memory_capability", "capability_semantics")
        slots.append("capability_status")
        sources.extend(("runtime_status", "technical_runtime", "documentation"))
    if recall:
        add_intent("memory_recall", "recall_semantics")
        slots.extend(("event_fact", "time_context", "source"))
        sources.extend(("conversation_archive", "active_memory", "journal_reflection", "canon", "inference"))
    if provenance:
        add_intent("provenance", "provenance_semantics")
        slots.extend(("source", "truth_status", "confidence"))
    if evidence_gap:
        add_intent("evidence_gap", "memory_evidence_gap_semantics")
        slots.append("evidence_gap")
    if technical_gap:
        add_intent("system_capability_gap", "technical_gap_object")
        slots.extend(("system_gap", "technical_evidence"))
        sources.extend(("source_code", "documentation", "runtime_status"))

    # Slot-level autobiographical questions.
    if _contains_any(folded, ("co powiedzialem ja", "co mowilem ja", "co ja powiedzialem")):
        slots.append("user_utterance")
    if _contains_any(folded, ("co odpowiedzialas ty", "co ty odpowiedzialas", "co odpowiedzialas")):
        slots.append("latka_utterance")
    if _contains_any(folded, ("co pozniej o tym myslalas", "pozniejsza refleksj", "co o tym myslalas")):
        slots.append("later_reflection")
    if _contains_any(folded, ("dlaczego", "czemu")) and preference:
        slots.append("preference_reason")

    # Plain capability question without an actual content request.
    memory_required = any(name in intents for name in ("memory_recall", "self_preference", "self_origin", "self_introspection", "identity_continuity"))
    if intents == ["memory_capability"]:
        memory_required = False

    if technical_gap:
        object_type = "system_capability_gap"
    elif recall:
        object_type = "autobiographical_memory"
    elif architecture:
        object_type = "memory_architecture"
    elif preference:
        object_type = "self_preference"
    elif origin:
        object_type = "self_origin"
    elif introspection:
        object_type = "self_reflection"
    elif identity_continuity:
        object_type = "identity_continuity"
    elif provenance:
        object_type = "source_provenance"
    else:
        object_type = "unknown"

    speech_act = "question" if "?" in text or _INTERROGATIVE_START.search(_clean(text)) else (
        "directive" if re.search(r"\b(?:przypomnij|przywolaj|powiedz|podaj|zaznacz)\b", folded) else "statement"
    )
    return QuestionComponent(
        component_id=f"q{index}",
        text=_clean(text),
        speech_act=speech_act,
        object_type=object_type,
        semantic_intents=tuple(dict.fromkeys(intents)),
        memory_required=memory_required,
        required_source_types=tuple(dict.fromkeys(sources)),
        requested_slots=tuple(dict.fromkeys(slots)),
        evidence=tuple(dict.fromkeys(evidence)),
    )


def analyse_utterance(text: str) -> UtteranceComponentReport:
    folded = re.sub(r"\s+", " ", _fold(text)).strip()
    components: list[str] = []
    for name, patterns in _COMPONENT_PATTERNS:
        if any(_fold(pattern) in folded for pattern in patterns):
            components.append(name)
    token_rules = (
        ("origin_creator", ("stworz", "powstal", "powstalas", "tworc", "urodzil")),
        ("rights_obligations", ("praw", "obowiaz", "wolno")),
        ("history", ("histori", "wczesniejs", "rozwijal")),
        ("preference", ("ulubion", "preferenc", "wolisz")),
        ("introspection", ("refleksj", "zastanawialas", "przeszlosc")),
        ("provenance", ("zrodlo", "skad wiesz", "z kanonu", "wnioskuj")),
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

    raw_questions = _split_meaningful_components(text)
    detailed = tuple(_component_semantics(part, idx + 1) for idx, part in enumerate(raw_questions))
    meaningful = tuple(
        component for component in detailed
        if component.semantic_intents or component.speech_act in {"question", "directive"}
    )
    semantic_intents = tuple(dict.fromkeys(intent for component in meaningful for intent in component.semantic_intents))
    required_sources = tuple(dict.fromkeys(source for component in meaningful for source in component.required_source_types))
    response_slots = tuple(dict.fromkeys(slot for component in meaningful for slot in component.requested_slots))
    # Compound is about independent goals/questions, not just keyword density.
    semantic_goal_count = sum(1 for component in meaningful if component.semantic_intents)
    compound = semantic_goal_count >= 2 or len({intent for intent in semantic_intents if intent not in {"provenance", "evidence_gap"}}) >= 2
    # Preserve generic multi-question capability/identity contracts even when
    # the specialized semantic layer does not assign an autobiographical label.
    # Keyword density inside one clause is not enough: a single recall directive
    # may legitimately mention history/provenance/module terms while remaining one goal.
    if len(components) >= 2 and len(raw_questions) >= 2:
        compound = True
    capability_only = bool(semantic_intents) and set(semantic_intents) <= {"memory_capability", "provenance"}
    system_capability_gap = "system_capability_gap" in semantic_intents

    return UtteranceComponentReport(
        components=tuple(dict.fromkeys(components)),
        negated_actions=tuple(dict.fromkeys(negated)),
        compound=compound,
        explicit_execution=explicit_execution,
        diagnostic_only=diagnostic_only,
        question_components=meaningful,
        semantic_intents=semantic_intents,
        required_source_types=required_sources,
        response_slots=response_slots,
        capability_only=capability_only,
        system_capability_gap=system_capability_gap,
    )


_COMPONENT_EVIDENCE: dict[str, tuple[str, ...]] = {
    "identity": ("jestem", "latka", "łatka", "jazn", "jaźń", "chatgpt", "runtime"),
    "capabilities": ("potraf", "umiem", "mogę", "moge", "możliwo", "zdoln", "capability"),
    "memory": ("pamię", "pamie", "wspomn", "recall", "archiw", "brak dowodu", "źród"),
    "preference": ("prefer", "ulubion", "lubi", "wolę", "wole", "brak dowodu"),
    "origin_creator": ("powsta", "urodz", "pochod", "stworz", "twórc", "tworc", "kanon", "runtime", "brak dowodu"),
    "introspection": ("refleks", "przeszł", "przeszl", "myśl", "mysl", "brak dowodu"),
    "provenance": ("źród", "zrod", "source", "provenance", "kanon", "pamię", "pamie", "wnios"),
    "history": ("histori", "wcześniej", "wczesniej", "wersj", "rozw", "kanon", "pamię", "pamie"),
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
        if evidence and not any(_fold(marker) in folded for marker in evidence):
            missing.append(component)
    return missing
