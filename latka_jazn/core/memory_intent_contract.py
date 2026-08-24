from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import re
import unicodedata
from typing import Any, Literal
from zoneinfo import ZoneInfo


MemoryOperation = Literal[
    "none",
    "capability",
    "experience_recall",
    "store_directive",
    "forget_directive",
]
TemporalPrecision = Literal["year", "month", "month_range"]
WARSAW = ZoneInfo("Europe/Warsaw")


@dataclass(frozen=True, slots=True)
class TemporalScope:
    """Half-open, source-derived boundary used by every memory layer."""

    start_utc: str
    end_utc_exclusive: str
    start_epoch: float
    end_epoch_exclusive: float
    precision: TemporalPrecision
    source_expression: str
    timezone_name: str = "Europe/Warsaw"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class MemoryIntentSemantics:
    schema_version: str
    operation: MemoryOperation
    content_requested: bool
    capability_only: bool
    explicit_recall: bool
    negated_recall: bool
    referential_followup: bool
    correction: bool
    subject: str
    temporal_scope: TemporalScope | None
    confidence: float
    evidence: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["evidence"] = list(self.evidence)
        return payload


MEMORY_EXPERIENCE_INTENTS = frozenset(
    {
        "memory_experience_question",
        "substantive_question_about_last_year",
    }
)
MEMORY_CONTENT_INTENTS = frozenset(
    {
        "memory_recall_request",
        "self_memory_recall_request",
        "user_memory_question",
        "user_memory_recall_request",
        "identity_memory_existence_compound_question",
        "identity_memory_question",
        "question_about_memory",
        "question_about_time_memory_and_experience",
        "continuity_question",
    }
) | MEMORY_EXPERIENCE_INTENTS
MEMORY_RETRIEVAL_INTENTS = MEMORY_CONTENT_INTENTS

_MONTH_FORMS: dict[str, int] = {
    "styczeń": 1, "styczen": 1, "stycznia": 1, "styczniu": 1, "styczniem": 1,
    "luty": 2, "lutego": 2, "lutym": 2,
    "marzec": 3, "marca": 3, "marcu": 3, "marcem": 3,
    "kwiecień": 4, "kwiecien": 4, "kwietnia": 4, "kwietniu": 4, "kwietniem": 4,
    "maj": 5, "maja": 5, "maju": 5, "majem": 5,
    "czerwiec": 6, "czerwca": 6, "czerwcu": 6, "czerwcem": 6,
    "lipiec": 7, "lipca": 7, "lipcu": 7, "lipcem": 7,
    "sierpień": 8, "sierpien": 8, "sierpnia": 8, "sierpniu": 8, "sierpniem": 8,
    "wrzesień": 9, "wrzesien": 9, "września": 9, "wrzesnia": 9,
    "wrześniu": 9, "wrzesniu": 9, "wrześniem": 9, "wrzesniem": 9,
    "październik": 10, "pazdziernik": 10, "października": 10, "pazdziernika": 10,
    "październiku": 10, "pazdzierniku": 10, "październikiem": 10, "pazdziernikiem": 10,
    "listopad": 11, "listopada": 11, "listopadzie": 11, "listopadem": 11,
    "grudzień": 12, "grudzien": 12, "grudnia": 12, "grudniu": 12, "grudniem": 12,
}
_MONTH_FORM_PATTERN = "|".join(
    re.escape(form) for form in sorted(_MONTH_FORMS, key=lambda item: (-len(item), item))
)
_MEMORY_STEMS = ("pamiet", "przypomn", "wspomin", "wspomnien", "rozmow")
_REFERENTIAL_PATTERNS = (
    r"\bwtedy\b",
    r"\btamt(?:o|ego|a|ej|ym)\b",
    r"\b(?:to|tego|tamto|tamtego) wspomnieni\w*\b",
    r"\bten temat\b",
    r"\bwroc(?:my)? do\b",
    r"\bona\b",
    r"\bten dzien\b",
)
_CORRECTION_PATTERNS = (
    r"\bnie tak\b",
    r"\bto bylo\b",
    r"\bwlasciwie\b",
    r"\bdokladniej\b",
    r"\bkoryguj",
    r"\bpopraw(?:ka|iam|ie)?\b",
    r"\bpomyl",
)


def _norm(text: str) -> str:
    value = unicodedata.normalize("NFKD", str(text or "").casefold())
    # NFKD does not decompose Polish stroked L, while the semantic patterns
    # intentionally operate on an ASCII-folded representation.
    value = value.replace("ł", "l")
    value = "".join(char for char in value if not unicodedata.combining(char))
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _utc_iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _scope(
    *,
    start_local: datetime,
    end_local: datetime,
    precision: TemporalPrecision,
    expression: str,
) -> TemporalScope:
    start_utc = start_local.astimezone(timezone.utc)
    end_utc = end_local.astimezone(timezone.utc)
    return TemporalScope(
        start_utc=_utc_iso(start_utc),
        end_utc_exclusive=_utc_iso(end_utc),
        start_epoch=start_utc.timestamp(),
        end_epoch_exclusive=end_utc.timestamp(),
        precision=precision,
        source_expression=expression.strip(),
    )


def _month_number(token: str) -> int | None:
    normalized = unicodedata.normalize("NFC", str(token or "").casefold()).strip()
    return _MONTH_FORMS.get(normalized)


def _month_start(year: int, month: int) -> datetime:
    return datetime(year, month, 1, tzinfo=WARSAW)


def _next_month(year: int, month: int) -> datetime:
    return _month_start(year + 1, 1) if month == 12 else _month_start(year, month + 1)


def parse_temporal_scope(
    text: str,
    *,
    now: datetime | None = None,
    previous_scope: TemporalScope | None = None,
) -> TemporalScope | None:
    """Parse Polish calendar language without turning it into an FTS term."""

    raw = str(text or "")
    normalized = _norm(raw)
    current = now or datetime.now(WARSAW)
    current = current.replace(tzinfo=WARSAW) if current.tzinfo is None else current.astimezone(WARSAW)

    explicit_years = [int(value) for value in re.findall(r"\b(?:19|20)\d{2}\b", normalized)]
    explicit_year = explicit_years[-1] if explicit_years else None
    relative_last_year = bool(
        re.search(
            r"\b(?:zeszl(?:y|ego|ym)|ubiegl(?:y|ego|ym)|minion(?:y|ego|ym)|poprzedni(?:m|ego)?) rok\w*",
            normalized,
        )
    )
    if relative_last_year:
        year = current.year - 1
        return _scope(
            start_local=_month_start(year, 1),
            end_local=_month_start(year + 1, 1),
            precision="year",
            expression=raw,
        )

    # Calendar nouns are parsed from NFC text that preserves Polish diacritics.
    # Prefix matching on the ASCII-folded text made unrelated words such as
    # "czerwony", "marzenia" and "mają" look like June, March and May.
    calendar_text = unicodedata.normalize("NFC", raw.casefold())
    month_words = [
        word
        for word in re.findall(r"\b[^\W\d_]+\b", calendar_text, flags=re.UNICODE)
        if word in _MONTH_FORMS
    ]
    months = [month for word in month_words if (month := _month_number(word)) is not None]
    if len(months) >= 2 and re.search(r"\b(?:od|miedzy)\b", normalized):
        start_month, end_month = months[0], months[1]
        if explicit_year is not None:
            end_year = explicit_year
            start_year = explicit_year if end_month >= start_month else explicit_year - 1
        else:
            end_year = current.year if end_month <= current.month else current.year - 1
            start_year = end_year if end_month >= start_month else end_year - 1
        return _scope(
            start_local=_month_start(start_year, start_month),
            end_local=_next_month(end_year, end_month),
            precision="month_range",
            expression=raw,
        )
    if months:
        month = months[0]
        if explicit_year is not None:
            year = explicit_year
        elif previous_scope is not None:
            year = datetime.fromtimestamp(
                previous_scope.start_epoch,
                tz=timezone.utc,
            ).astimezone(WARSAW).year
        else:
            year = current.year if month <= current.month else current.year - 1
        return _scope(
            start_local=_month_start(year, month),
            end_local=_next_month(year, month),
            precision="month",
            expression=raw,
        )
    if explicit_year is not None:
        return _scope(
            start_local=_month_start(explicit_year, 1),
            end_local=_month_start(explicit_year + 1, 1),
            precision="year",
            expression=raw,
        )
    if previous_scope is not None and any(re.search(pattern, normalized) for pattern in _REFERENTIAL_PATTERNS):
        return previous_scope
    return None


def _subject(normalized: str) -> str:
    if re.search(r"\b(?:o mnie|moje wspomnien|moja pamiec|co ja)\b", normalized):
        return "user"
    if re.search(r"\b(?:nasz\w* rozmow|wspoln\w*|razem|miedzy nami)\b", normalized):
        return "shared"
    if re.search(r"\b(?:twoj\w*|swoj\w* zyci|ty pamiet|co pamietasz)\b", normalized):
        return "self"
    return "experience"


def analyze_memory_intent(
    text: str,
    *,
    previous_text: str | None = None,
    now: datetime | None = None,
) -> MemoryIntentSemantics:
    raw = str(text or "")
    normalized = _norm(raw)
    previous_temporal = parse_temporal_scope(previous_text or "", now=now) if previous_text else None
    temporal = parse_temporal_scope(raw, now=now, previous_scope=previous_temporal)
    evidence: list[str] = []
    referential = any(re.search(pattern, normalized) for pattern in _REFERENTIAL_PATTERNS)
    correction = any(re.search(pattern, normalized) for pattern in _CORRECTION_PATTERNS)
    if referential:
        evidence.append("referential_followup")
    if correction:
        evidence.append("user_correction")
    if temporal is not None:
        evidence.append(f"temporal:{temporal.precision}")

    forget = bool(
        re.search(r"\b(?:zapomnij|usun\w* z pamieci|nie (?:pamietaj|zapamietuj))\b", normalized)
    )
    if forget:
        evidence.append("forget_directive")
        return MemoryIntentSemantics(
            "memory_intent/v1", "forget_directive", False, False, False, True,
            referential, correction, _subject(normalized), temporal, 0.96, tuple(evidence),
        )
    store = bool(re.search(r"\b(?:zapamietaj|pamietaj)(?: prosze)?(?: ze| o| to|,|$)", normalized))
    if store:
        evidence.append("store_directive")
        return MemoryIntentSemantics(
            "memory_intent/v1", "store_directive", False, False, False, False,
            referential, correction, _subject(normalized), temporal, 0.96, tuple(evidence),
        )

    negated = bool(
        re.search(
            r"\bnie(?: chce| chcial\w*| prosze)? "
            r"(?:wspomin\w*|przypomin\w*|wrac\w*|pamiet\w*|szuk\w*|poszuk\w*|odnajd\w*|znajd\w*)",
            normalized,
        )
    )
    positive_after_negation = bool(
        re.search(
            r"\b(?:ale|tylko|za to|natomiast)\b.*\b(?:powspomin|wspomin|przypomn|pamiet)",
            normalized,
        )
    )
    if negated and not positive_after_negation:
        evidence.append("recall_negated")
        return MemoryIntentSemantics(
            "memory_intent/v1", "none", False, False, False, True,
            referential, correction, _subject(normalized), temporal, 0.93, tuple(evidence),
        )

    imperative_recall = bool(
        re.search(r"\b(?:powspomin\w*|przypomnij(?: sobie)?|wroc(?:my)? do (?:tamtego|tego) wspomnienia)\b", normalized)
    )
    polite_recall = bool(
        re.search(
            r"\bczy (?:mozesz|moglabys|jestes w stanie)(?: mi)? "
            r"(?:(?:sobie )?przypomniec|przypomniec sobie|powspominac)\b",
            normalized,
        )
        and (
            temporal is not None
            or re.search(r"\b(?:rozmow|wydarz|chwil|spotkan|wspomnien)\w*\b", normalized)
        )
    )
    content_question = bool(
        re.search(r"\b(?:co|jakie|ktore|ile) (?:ty )?(?:pamiet\w*|wspomin\w*|przypomin\w*)", normalized)
    )
    past_or_present_recall = bool(
        re.search(r"\b(?:pamietalas|pamietasz|wspominasz|przypominasz sobie)\b", normalized)
        and (temporal is not None or referential or re.search(r"\b(?:rozmow|dzien|wydarz|chwil|spotkan|wspomnien)\w*\b", normalized))
    )
    search_recall = bool(
        re.search(
            r"\b(?:(?:chce|prosze) )?"
            r"(?:szukaj|poszukaj|odnajdz|odnalezc|znajdz|znalezc)\b"
            r".*\bwspomnieni\w*\b",
            normalized,
        )
    )
    capability = bool(
        re.search(r"\bczy (?:w ogole )?(?:potrafisz|umiesz|mozesz|jestes w stanie)\b.*\b(?:pamiet|wspomin|przypomin)", normalized)
        or re.fullmatch(r"czy (?:ty )?pamietasz", normalized) is not None
    )
    actual_recall = (
        imperative_recall
        or polite_recall
        or content_question
        or past_or_present_recall
        or search_recall
    )
    if actual_recall:
        evidence.append("explicit_content_recall")
    if capability and not imperative_recall and not polite_recall and not content_question:
        evidence.append("capability_question")
        return MemoryIntentSemantics(
            "memory_intent/v1", "capability", False, True, False, False,
            referential, correction, _subject(normalized), temporal, 0.91, tuple(evidence),
        )

    previous_recall = False
    if previous_text and (referential or correction):
        previous_recall = analyze_memory_intent(previous_text, now=now).content_requested
    if previous_recall:
        evidence.append("inherited_memory_anchor")
    content_requested = actual_recall or previous_recall
    operation: MemoryOperation = "experience_recall" if content_requested else "none"
    confidence = 0.95 if actual_recall else (0.82 if previous_recall else 0.28)
    if not content_requested and any(stem in normalized for stem in _MEMORY_STEMS):
        evidence.append("memory_language_without_content_request")
        confidence = 0.48
    return MemoryIntentSemantics(
        "memory_intent/v1", operation, content_requested, False, actual_recall, False,
        referential, correction, _subject(normalized), temporal, confidence, tuple(evidence),
    )


def intent_requires_memory_content(intent: str | None) -> bool:
    return str(intent or "").strip() in MEMORY_CONTENT_INTENTS


def has_explicit_memory_recall(text: str, *, previous_text: str | None = None) -> bool:
    return analyze_memory_intent(text, previous_text=previous_text).content_requested


def strip_temporal_language(text: str, scope: TemporalScope | None) -> str:
    """Remove calendar-control tokens before lexical FTS planning."""

    value = str(text or "")
    if scope is None:
        return value
    value = re.sub(r"\b(?:19|20)\d{2}(?:\s*r(?:oku)?\.?)?\b", " ", value, flags=re.IGNORECASE)
    value = re.sub(
        r"\b(?:ze?\s+)?(?:zesz(?:łego|lego|łym|lym)|ubieg(?:łego|lego|łym|lym)|minion(?:ego|ym)|poprzedniego)\s+roku\b",
        " ", value, flags=re.IGNORECASE,
    )
    value = re.sub(
        rf"\b(?:od|do|miedzy|między)?\s*(?:{_MONTH_FORM_PATTERN})\b",
        " ", value, flags=re.IGNORECASE,
    )
    return re.sub(r"\s+", " ", value).strip()


__all__ = [
    "MEMORY_CONTENT_INTENTS", "MEMORY_EXPERIENCE_INTENTS", "MEMORY_RETRIEVAL_INTENTS", "MemoryIntentSemantics",
    "TemporalScope", "analyze_memory_intent", "has_explicit_memory_recall",
    "intent_requires_memory_content", "parse_temporal_scope", "strip_temporal_language",
]
