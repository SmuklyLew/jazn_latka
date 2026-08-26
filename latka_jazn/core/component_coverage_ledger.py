from __future__ import annotations

from dataclasses import asdict, dataclass, field
import re
import unicodedata
from typing import Any

from latka_jazn.nlp.utterance_components import QuestionComponent, analyse_utterance
from latka_jazn.version import schema_version


SCHEMA_VERSION = schema_version("component_coverage_ledger")


@dataclass(slots=True)
class ComponentCoverageRecord:
    component_id: str
    component_text: str
    semantic_intents: list[str] = field(default_factory=list)
    requested_slots: list[str] = field(default_factory=list)
    status: str = "missing"
    matched_semantic_intents: list[str] = field(default_factory=list)
    missing_semantic_intents: list[str] = field(default_factory=list)
    anchor_hits: list[str] = field(default_factory=list)
    evidence_gap_declared: bool = False
    evidence: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_STOPWORDS = {
    "oraz", "ktore", "które", "jakie", "jaki", "jaka", "kiedy", "dlaczego",
    "czemu", "skad", "skąd", "tego", "tobie", "twoja", "twoje", "twoim",
    "swoja", "swoją", "swoje", "sobie", "jestes", "jesteś", "jesli", "jeśli",
    "powiedz", "prosze", "proszę", "konkretnie", "naprawde", "naprawdę",
    "pytania", "pytanie", "elementy", "element", "takie", "taka", "taki",
}

_INTENT_MARKERS: dict[str, tuple[str, ...]] = {
    "self_preference": (
        "preferenc", "ulubion", "najbardziej lub", "wolę", "wole", "lubię", "lubie",
        "wybieram", "podoba mi się", "podoba mi sie",
    ),
    "self_origin": (
        "powsta", "początek", "poczatek", "pochodz", "stworz", "źródło powstania",
        "zrodlo powstania", "kanoniczny początek", "kanoniczny poczatek", "techniczny początek",
        "techniczny poczatek", "nie biolog",
    ),
    "self_introspection": (
        "refleks", "zastanaw", "myślę", "mysle", "myślałam", "myslalam", "później",
        "pozniej", "wniosek", "z perspektywy",
    ),
    "identity_continuity": (
        "ciągło", "ciaglo", "tożsamo", "tozsamo", "ta sama", "nadal", "kanon",
        "ciągłość", "ciaglosc",
    ),
    "memory_architecture": (
        "architektur", "implementac", "gateway", "runtime_write", "warstw", "moduł pamięci",
        "modul pamieci", "źródło techniczne", "zrodlo techniczne",
    ),
    "memory_capability": (
        "potraf", "mogę pamiętać", "moge pamietac", "zdolność pamięci", "zdolnosc pamieci",
        "możliwość pamięci", "mozliwosc pamieci",
    ),
    "memory_recall": (
        "pamiętam", "pamietam", "wspomin", "przypomin", "odzysk", "archiw", "w pamięci",
        "w pamieci", "rozmow",
    ),
    "provenance": (
        "źród", "zrod", "provenance", "prowenienc", "z archiwum", "z kanonu",
        "wnioskuj", "truth", "pewność", "pewnosc",
    ),
    "evidence_gap": (
        "brak dowodu", "brak potwierd", "evidence_gap", "evidence gap", "nie znalaz",
        "nie mam źród", "nie mam zrod", "nie mam w pamięci", "nie mam w pamieci",
        "nie mogę potwierdzić", "nie moge potwierdzic",
    ),
    "system_capability_gap": (
        "czego brakuje", "niepełn", "niepeln", "brak implementac", "brak funkcj",
        "moduł", "modul", "kod", "system", "runtime",
    ),
}

_GAP_MARKERS = _INTENT_MARKERS["evidence_gap"]


def _fold(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(text or ""))
    folded = "".join(ch for ch in normalized if not unicodedata.combining(ch)).lower()
    return folded.replace("ł", "l")


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]{4,}", _fold(text))


def _anchors(component: QuestionComponent) -> list[str]:
    anchors: list[str] = []
    for token in _tokens(component.text):
        if token in _STOPWORDS or token in anchors:
            continue
        anchors.append(token)
    return anchors[:10]


def _matches_any(folded_body: str, markers: tuple[str, ...]) -> bool:
    return any(_fold(marker) in folded_body for marker in markers)


def build_component_coverage_ledger(
    *,
    user_text: str,
    body: str,
    coverage_required: bool,
) -> dict[str, Any]:
    """Build a fail-closed per-component coverage ledger for visible output.

    The ledger does not infer facts.  It only checks whether each independently
    parsed question component has a response signal for its semantic goal or an
    explicit evidence-gap declaration.  The component id is therefore carried
    all the way to final answer validation instead of being reduced to one global
    `compound=True` flag.
    """

    report = analyse_utterance(user_text)
    components = list(report.question_components)
    folded_body = _fold(body)
    records: list[ComponentCoverageRecord] = []

    for component in components:
        semantic_intents = [str(value) for value in component.semantic_intents]
        anchors = _anchors(component)
        anchor_hits = [anchor for anchor in anchors if anchor in folded_body]
        matched: list[str] = []
        missing: list[str] = []
        evidence: list[str] = []

        for intent in semantic_intents:
            markers = _INTENT_MARKERS.get(intent, ())
            if markers and _matches_any(folded_body, markers):
                matched.append(intent)
                evidence.append(f"semantic:{intent}")
            elif intent == "provenance" and _matches_any(folded_body, _INTENT_MARKERS["provenance"]):
                matched.append(intent)
                evidence.append("semantic:provenance")
            elif markers:
                missing.append(intent)

        gap_declared = _matches_any(folded_body, _GAP_MARKERS)
        # A generic "brak danych" cannot silently satisfy every component.  It
        # must be tied either to a component anchor or to a component whose own
        # semantic contract explicitly asks for an evidence gap.
        gap_applies = bool(
            gap_declared
            and (
                anchor_hits
                or "evidence_gap" in semantic_intents
                or any(intent in matched for intent in ("self_origin", "memory_recall", "provenance"))
            )
        )

        if not semantic_intents:
            covered = bool(anchor_hits)
        else:
            covered = not missing and bool(matched or anchor_hits)

        if covered:
            status = "covered"
        elif gap_applies:
            status = "evidence_gap"
            evidence.append("explicit_evidence_gap")
        else:
            status = "missing"

        records.append(
            ComponentCoverageRecord(
                component_id=component.component_id,
                component_text=component.text,
                semantic_intents=semantic_intents,
                requested_slots=[str(value) for value in component.requested_slots],
                status=status,
                matched_semantic_intents=matched,
                missing_semantic_intents=missing,
                anchor_hits=anchor_hits,
                evidence_gap_declared=gap_applies,
                evidence=evidence,
            )
        )

    missing_ids = [record.component_id for record in records if record.status == "missing"]
    complete = not missing_ids if coverage_required else True
    return {
        "schema_version": SCHEMA_VERSION,
        "coverage_required": bool(coverage_required),
        "required_component_ids": [record.component_id for record in records],
        "complete": bool(complete),
        "missing_component_ids": missing_ids,
        "records": [record.to_dict() for record in records],
        "truth_boundary": (
            "Każdy component_id musi mieć pokrycie semantyczne albo jawny evidence_gap; "
            "brak jednego komponentu blokuje finalizację, gdy coverage_required=true."
        ),
    }


__all__ = [
    "SCHEMA_VERSION",
    "ComponentCoverageRecord",
    "build_component_coverage_ledger",
]
