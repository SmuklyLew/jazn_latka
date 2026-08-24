from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import hashlib
import math
import re
import unicodedata
from typing import Any, Iterable, Mapping

from latka_jazn.core.memory_intent_contract import (
    analyze_memory_intent,
    intent_requires_memory_content,
)
from latka_jazn.version import schema_version

SCHEMA_VERSION = schema_version("dialogue_task_state")
DEFAULT_TASK_TTL_SECONDS = 21600
MAX_MEMORY_ANCHOR_IDENTIFIERS = 16
MAX_MEMORY_CORRECTIONS = 8
MAX_MEMORY_CORRECTION_TEXT = 320

_DIACRITIC_MAP = str.maketrans("ąćęłńóśźżĄĆĘŁŃÓŚŹŻ", "acelnoszzACELNOSZZ")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", str(text or "")).strip().lower())


def _fold(text: str) -> str:
    return _normalize(text).translate(_DIACRITIC_MAP)


def _task_key(intent: str, route: str, goal: str) -> str:
    material = f"{intent}\n{route}\n{_fold(goal)[:320]}".encode("utf-8")
    return hashlib.sha256(material).hexdigest()[:24]


def _text_sha256(text: str) -> str:
    return hashlib.sha256(str(text or "").encode("utf-8", errors="surrogatepass")).hexdigest()


def _stable_memory_item_id(*, memory_type: str, source: str, timestamp: Any, content: str) -> str:
    material = "\n".join((memory_type, source, str(timestamp or ""), content)).encode("utf-8")
    return "memory_" + hashlib.sha256(material).hexdigest()[:24]


def _optional_text(value: Any, *, limit: int = 320) -> str | None:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    return text[:limit] or None


def _bounded_unique_texts(value: Any, *, limit: int = MAX_MEMORY_ANCHOR_IDENTIFIERS) -> list[str]:
    if isinstance(value, (str, bytes, Mapping)) or not isinstance(value, Iterable):
        return []
    result: list[str] = []
    for raw in value:
        item = _optional_text(raw, limit=160)
        if item and item not in result:
            result.append(item)
        if len(result) >= limit:
            break
    return result


def _bounded_hashes(value: Any, *, limit: int = MAX_MEMORY_ANCHOR_IDENTIFIERS) -> list[str]:
    hashes: list[str] = []
    for item in _bounded_unique_texts(value, limit=limit):
        normalized = item.lower()
        if _SHA256_RE.fullmatch(normalized) and normalized not in hashes:
            hashes.append(normalized)
    return hashes


def _temporal_scope(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    start_utc = _optional_text(value.get("start_utc"), limit=64)
    end_utc = _optional_text(value.get("end_utc_exclusive"), limit=64)
    precision = _optional_text(value.get("precision"), limit=32)
    expression = _optional_text(value.get("source_expression"), limit=160)
    timezone_name = _optional_text(value.get("timezone_name"), limit=64)
    raw_start_epoch = value.get("start_epoch")
    raw_end_epoch = value.get("end_epoch_exclusive")
    if (
        isinstance(raw_start_epoch, bool)
        or not isinstance(raw_start_epoch, (str, int, float))
        or isinstance(raw_end_epoch, bool)
        or not isinstance(raw_end_epoch, (str, int, float))
    ):
        return None
    try:
        start_epoch = float(raw_start_epoch)
        end_epoch = float(raw_end_epoch)
    except ValueError:
        return None
    if (
        not start_utc
        or not end_utc
        or precision not in {"year", "month", "month_range"}
        or not math.isfinite(start_epoch)
        or not math.isfinite(end_epoch)
        or start_epoch >= end_epoch
    ):
        return None
    return {
        "start_utc": start_utc,
        "end_utc_exclusive": end_utc,
        "start_epoch": start_epoch,
        "end_epoch_exclusive": end_epoch,
        "precision": precision,
        "source_expression": expression or "",
        "timezone_name": timezone_name or "Europe/Warsaw",
    }


def _looks_like_memory_task(intent: str | None, route: str | None) -> bool:
    intent_value = str(intent or "").strip()
    folded_intent = _fold(intent_value)
    route_value = _fold(str(route or ""))
    return (
        intent_requires_memory_content(intent_value)
        or ("memory" in folded_intent and "capability" not in folded_intent)
        or "memory_recall" in route_value
        or "memory_experience" in route_value
    )


def _sanitize_correction(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    text = _optional_text(value.get("text"), limit=MAX_MEMORY_CORRECTION_TEXT)
    supplied_hash = _optional_text(value.get("text_sha256"), limit=64)
    computed_hash = _text_sha256(text) if text else ""
    if supplied_hash and (
        not _SHA256_RE.fullmatch(supplied_hash.lower())
        or (computed_hash and supplied_hash.lower() != computed_hash)
    ):
        return None
    text_hash = computed_hash or str(supplied_hash or "").lower()
    if not _SHA256_RE.fullmatch(text_hash):
        return None
    overlay: dict[str, Any] = {
        "text": text or "",
        "text_sha256": text_hash,
        "asserted_at_utc": _optional_text(value.get("asserted_at_utc"), limit=64) or _utc_now(),
        "source_kind": "current_turn_user_assertion",
        "truth_status": "user_asserted_overlay",
        "historical_source_unchanged": True,
    }
    scope = _temporal_scope(value.get("temporal_scope"))
    if scope is not None:
        overlay["temporal_scope"] = scope
    return overlay


def _bounded_corrections(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, (str, bytes, Mapping)) or not isinstance(value, Iterable):
        return []
    result: list[dict[str, Any]] = []
    for raw in value:
        correction = _sanitize_correction(raw)
        if correction is not None:
            result.append(correction)
    return result[-MAX_MEMORY_CORRECTIONS:]


@dataclass(slots=True)
class DialogueTaskState:
    """Durable execution state with a source-preserving memory anchor.

    ``memory_*`` anchor fields describe the original source-backed recall task.
    They are deliberately separate from current-turn corrections: a user
    correction can guide the next answer, but cannot silently rewrite the
    historical query, temporal boundary, source IDs, item IDs or excerpt hashes.
    """

    active: bool = False
    task_key: str | None = None
    active_goal: str | None = None
    active_intent: str | None = None
    active_route: str | None = None
    expected_next_action: str | None = None
    execution_status: str = "idle"
    referents: list[str] = field(default_factory=list)
    topic_stack: list[str] = field(default_factory=list)
    confidence: float = 0.0
    opened_at_utc: str | None = None
    updated_at_utc: str | None = None
    turn_count: int = 0
    source: str = "runtime_dialogue"

    memory_anchor_status: str = "none"
    memory_anchor_integrity: str = "none"
    memory_query: str | None = None
    memory_query_sha256: str | None = None
    memory_anchor_goal: str | None = None
    memory_anchor_intent: str | None = None
    memory_anchor_route: str | None = None
    memory_temporal_scope: dict[str, Any] | None = None
    memory_source_ids: list[str] = field(default_factory=list)
    memory_item_ids: list[str] = field(default_factory=list)
    memory_excerpt_hashes: list[str] = field(default_factory=list)
    memory_evidence_bound: bool = False
    memory_evidence_bound_at_utc: str | None = None
    memory_corrections: list[dict[str, Any]] = field(default_factory=list)

    schema_version: str = SCHEMA_VERSION
    truth_boundary: str = (
        "Stan zadania opisuje aktywny cel rozmowy. Kotwica pamięci zachowuje niezmienione "
        "identyfikatory źródeł i skróty treści; korekty użytkownika są osobnymi, nieweryfikowanymi "
        "nakładkami i nie są autobiograficznym wspomnieniem ani dowodem wykonania zadania."
    )

    @property
    def has_memory_anchor(self) -> bool:
        return self.memory_anchor_integrity != "invalid" and bool(
            self.memory_query or self.memory_anchor_goal or self.memory_temporal_scope
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def with_memory_evidence(
        self,
        *,
        source_ids: Iterable[str] = (),
        item_ids: Iterable[str] = (),
        excerpt_hashes: Iterable[str] = (),
    ) -> "DialogueTaskState":
        """Bind retrieval evidence once; later turns cannot replace the anchor."""

        copied = DialogueTaskState.from_mapping(self.to_dict())
        if not copied.has_memory_anchor or copied.memory_evidence_bound:
            return copied
        copied.memory_source_ids = _bounded_unique_texts(source_ids)
        copied.memory_item_ids = _bounded_unique_texts(item_ids)
        copied.memory_excerpt_hashes = _bounded_hashes(excerpt_hashes)
        copied.memory_evidence_bound = True
        copied.memory_evidence_bound_at_utc = _utc_now()
        copied.updated_at_utc = copied.memory_evidence_bound_at_utc
        return copied

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any] | None) -> "DialogueTaskState":
        if not isinstance(value, Mapping):
            return cls()
        referents = _bounded_unique_texts(value.get("referents"), limit=8)
        topic_stack = _bounded_unique_texts(value.get("topic_stack"), limit=8)
        active_goal = _optional_text(value.get("active_goal"))
        active_intent = _optional_text(value.get("active_intent"), limit=96)
        active_route = _optional_text(value.get("active_route"), limit=96)
        memory_query = _optional_text(value.get("memory_query"))
        memory_anchor_goal = _optional_text(value.get("memory_anchor_goal"))
        if not (memory_query or memory_anchor_goal) and _looks_like_memory_task(active_intent, active_route):
            # Safe migration of pre-v16.3 task snapshots: the prior active goal
            # becomes the original anchor exactly once.
            memory_query = active_goal
            memory_anchor_goal = active_goal
        elif memory_query and not memory_anchor_goal:
            memory_anchor_goal = memory_query
        elif memory_anchor_goal and not memory_query:
            memory_query = memory_anchor_goal
        supplied_query_hash = _optional_text(value.get("memory_query_sha256"), limit=64)
        persisted_integrity = _optional_text(value.get("memory_anchor_integrity"), limit=32)
        query_hash: str | None = None
        anchor_integrity = persisted_integrity if persisted_integrity in {"valid", "legacy_migrated", "invalid"} else "none"
        if memory_query:
            computed_query_hash = _text_sha256(memory_query)
            if supplied_query_hash:
                supplied_query_hash = supplied_query_hash.lower()
                if (
                    not _SHA256_RE.fullmatch(supplied_query_hash)
                    or supplied_query_hash != computed_query_hash
                ):
                    anchor_integrity = "invalid"
                    query_hash = supplied_query_hash if _SHA256_RE.fullmatch(supplied_query_hash) else None
                else:
                    query_hash = supplied_query_hash
                    anchor_integrity = (
                        anchor_integrity if anchor_integrity in {"valid", "legacy_migrated"} else "valid"
                    )
            else:
                query_hash = computed_query_hash
                anchor_integrity = "legacy_migrated"
        elif anchor_integrity != "invalid":
            anchor_integrity = "none"
        try:
            confidence = max(0.0, min(1.0, float(value.get("confidence") or 0.0)))
        except (TypeError, ValueError):
            confidence = 0.0
        try:
            turn_count = max(0, int(value.get("turn_count") or 0))
        except (TypeError, ValueError):
            turn_count = 0
        anchor_status = _optional_text(value.get("memory_anchor_status"), limit=24)
        anchor_invalid = anchor_integrity == "invalid"
        if anchor_invalid:
            memory_query = None
            memory_anchor_goal = None
            anchor_status = "invalid"
        elif memory_query and anchor_status not in {"active", "suspended"}:
            anchor_status = "active" if bool(value.get("active")) else "suspended"
        active = bool(value.get("active"))
        execution_status = _optional_text(value.get("execution_status"), limit=32) or "idle"
        if anchor_invalid and _looks_like_memory_task(active_intent, active_route):
            active = False
            execution_status = "invalid_memory_anchor"
        source_ids = [] if anchor_invalid else _bounded_unique_texts(value.get("memory_source_ids"))
        item_ids = [] if anchor_invalid else _bounded_unique_texts(value.get("memory_item_ids"))
        excerpt_hashes = [] if anchor_invalid else _bounded_hashes(value.get("memory_excerpt_hashes"))
        evidence_bound = bool(value.get("memory_evidence_bound")) or bool(
            source_ids or item_ids or excerpt_hashes
        )
        return cls(
            active=active,
            task_key=_optional_text(value.get("task_key"), limit=64),
            active_goal=active_goal,
            active_intent=active_intent,
            active_route=active_route,
            expected_next_action=_optional_text(value.get("expected_next_action"), limit=64),
            execution_status=execution_status,
            referents=referents,
            topic_stack=topic_stack,
            confidence=confidence,
            opened_at_utc=_optional_text(value.get("opened_at_utc"), limit=64),
            updated_at_utc=_optional_text(value.get("updated_at_utc"), limit=64),
            turn_count=turn_count,
            source=_optional_text(value.get("source"), limit=64) or "runtime_dialogue",
            memory_anchor_status=anchor_status or "none",
            memory_anchor_integrity=anchor_integrity,
            memory_query=memory_query,
            memory_query_sha256=query_hash.lower() if query_hash else None,
            memory_anchor_goal=memory_anchor_goal,
            memory_anchor_intent=(
                None
                if anchor_invalid
                else (
                    _optional_text(value.get("memory_anchor_intent"), limit=96)
                    or (active_intent if memory_query and _looks_like_memory_task(active_intent, active_route) else None)
                )
            ),
            memory_anchor_route=(
                None
                if anchor_invalid
                else (
                    _optional_text(value.get("memory_anchor_route"), limit=96)
                    or (active_route if memory_query and _looks_like_memory_task(active_intent, active_route) else None)
                )
            ),
            memory_temporal_scope=(None if anchor_invalid else _temporal_scope(value.get("memory_temporal_scope"))),
            memory_source_ids=source_ids,
            memory_item_ids=item_ids,
            memory_excerpt_hashes=excerpt_hashes,
            memory_evidence_bound=evidence_bound if not anchor_invalid else False,
            memory_evidence_bound_at_utc=(
                _optional_text(value.get("memory_evidence_bound_at_utc"), limit=64)
                if evidence_bound and not anchor_invalid
                else None
            ),
            memory_corrections=([] if anchor_invalid else _bounded_corrections(value.get("memory_corrections"))),
            schema_version=_optional_text(value.get("schema_version"), limit=64) or SCHEMA_VERSION,
            truth_boundary=_optional_text(value.get("truth_boundary"), limit=640) or cls().truth_boundary,
        )


@dataclass(slots=True)
class DialogueTaskResolution:
    inherited: bool
    resolved_intent: str | None = None
    resolved_route: str | None = None
    resolution_type: str = "current_turn"
    confidence: float = 0.0
    evidence: list[str] = field(default_factory=list)
    task_state: DialogueTaskState = field(default_factory=DialogueTaskState)
    requires_clarification: bool = False
    schema_version: str = SCHEMA_VERSION
    truth_boundary: str = (
        "Dziedziczenie celu jest dozwolone tylko dla jawnej kontynuacji zgodnej z kotwicą. "
        "Korekta użytkownika pozostaje nakładką, a oryginalne źródła pamięci nie są nadpisywane."
    )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        return payload


class DialogueTaskStateResolver:
    """Resolve execution and memory references against structured durable state."""

    _EXECUTE_MARKERS = (
        "zrob to", "zrob to teraz", "zrob to wszystko", "wykonaj to", "zacznij teraz",
        "zacznij", "dzialaj", "rob to", "przejdz do tego", "mozesz to zrobic",
        "zajmij sie tym", "zrob to sama", "zrob to samodzielnie",
    )
    _CONTINUE_MARKERS = (
        "kontynuuj", "jedz dalej", "idz dalej", "dalej", "co dalej", "wroc do tego",
        "wracaj do tego", "dokonczy", "dokonc", "ciagnij dalej",
    )
    _AGREEMENT_MARKERS = (
        "zgadzam sie", "tak", "dobrze", "w porzadku", "ok", "okej", "jasne",
        "dokladnie", "zgoda",
    )
    _TOPIC_SWITCH_MARKERS = (
        "zmienmy temat", "nowy temat", "inna sprawa", "zostawmy ten temat", "zostaw to",
        "porozmawiajmy teraz o", "a teraz porozmawiajmy o", "przejdzmy do innego tematu",
    )
    _HARD_CANCEL_MARKERS = (
        "nie rob tego", "anuluj", "stop", "przestan", "zapomnij o tym", "zamknij zadanie",
        "nie chce do tego wracac", "nie wracajmy do tego", "nie wspominaj", "nie przypominaj",
    )
    _MEMORY_REFERENCE_MARKERS = (
        "wtedy", "tamto", "tamtego", "tamtej", "tamtym", "to wspomnienie",
        "tego wspomnienia", "tamtego wspomnienia", "ten temat", "tamten temat",
        "tamte rozmowy", "tamtego dnia", "co czulas", "jak sie wtedy czulas",
        "co jeszcze", "i potem", "a dalej", "pozniej",
    )
    _MEMORY_RETURN_MARKERS = (
        "wrocmy do tamtego wspomnienia", "wrocmy do tego wspomnienia",
        "wroc do tamtego wspomnienia", "wroc do tego wspomnienia",
        "wracajac do tamtego wspomnienia", "wrocmy do tamtego tematu",
    )
    _CORRECTION_MARKERS = (
        "nie tak", "to bylo", "wlasciwie", "dokladniej", "koryguj", "poprawiam",
        "poprawka", "pomylilas", "pomyliles", "chodzilo mi", "nie wtedy",
    )
    _CURRENT_TURN_SPECIAL_MARKERS = (
        "ktora godzina", "jaka pogoda", "kim jestes", "z kim rozmawiam", "czy dziala runtime",
        "uruchom ponownie", "zrestartuj", "sprawdz status",
    )
    _ACTIONABLE_INTENT_SUFFIXES = (
        "_request", "_execution_request", "_recall_request", "_formatting", "_analysis",
        "_advice", "_audit_request",
    )
    _NON_EXECUTABLE_INTENTS = {
        "ordinary_conversation", "short_free_dialogue", "standalone_greeting", "casual_greeting",
        "self_state_question", "reciprocal_self_state_question", "current_time_question",
        "runtime_health_check", "runtime_activation_status_question", "presence_check",
    }

    @classmethod
    def _contains_any(cls, folded: str, markers: tuple[str, ...]) -> bool:
        return any(marker in folded for marker in markers)

    @classmethod
    def _looks_like_contextual_execution(cls, folded: str) -> tuple[bool, str]:
        execute = cls._contains_any(folded, cls._EXECUTE_MARKERS)
        continuation = cls._contains_any(folded, cls._CONTINUE_MARKERS)
        agreement = cls._contains_any(folded, cls._AGREEMENT_MARKERS)
        if execute:
            return True, "execute"
        if continuation:
            return True, "continue"
        if agreement and any(marker in folded for marker in ("teraz", "zaczn", "zrob", "wykon", "dzial")):
            return True, "execute"
        return False, "none"

    @classmethod
    def _memory_reference_kind(cls, folded: str, *, previous_query: str | None = None) -> str | None:
        if cls._contains_any(folded, cls._MEMORY_RETURN_MARKERS):
            return "return"
        if cls._contains_any(folded, cls._CORRECTION_MARKERS):
            return "correction"
        word_count = len(folded.split())
        if re.fullmatch(r"(?:a )?to\??", folded):
            return "followup"
        if word_count <= 10 and re.search(r"\bco z (?:tym|tamtym)\b", folded):
            return "followup"
        if word_count <= 18 and cls._contains_any(folded, cls._MEMORY_REFERENCE_MARKERS):
            return "followup"
        if word_count <= 8 and re.search(r"\b(?:on|ona|ono|jej|nia|jego|ich|nim|niej|nimi)\b", folded):
            return "followup"
        if previous_query:
            semantics = analyze_memory_intent(folded, previous_text=previous_query)
            if semantics.temporal_scope is not None and not semantics.explicit_recall and word_count <= 8:
                return "followup"
        return None

    @classmethod
    def _action_for_intent(cls, intent: str, route: str) -> str | None:
        intent_folded = _fold(intent)
        route_folded = _fold(route)
        if _looks_like_memory_task(intent, route):
            return "recall"
        if "research" in intent_folded:
            return "research"
        if "update" in intent_folded or "repair" in intent_folded or "update" in route_folded:
            return "execute_update"
        if "creative" in intent_folded or "format" in intent_folded:
            return "create"
        if "audit" in intent_folded:
            return "audit"
        if intent and intent not in cls._NON_EXECUTABLE_INTENTS and (
            intent.endswith(cls._ACTIONABLE_INTENT_SUFFIXES) or "request" in intent
        ):
            return "execute"
        return None

    @staticmethod
    def _copy_anchor(target: DialogueTaskState, previous: DialogueTaskState, *, status: str) -> None:
        target.memory_anchor_status = status
        target.memory_anchor_integrity = previous.memory_anchor_integrity
        target.memory_query = previous.memory_query
        target.memory_query_sha256 = previous.memory_query_sha256
        target.memory_anchor_goal = previous.memory_anchor_goal
        target.memory_anchor_intent = previous.memory_anchor_intent
        target.memory_anchor_route = previous.memory_anchor_route
        target.memory_temporal_scope = (
            dict(previous.memory_temporal_scope) if previous.memory_temporal_scope is not None else None
        )
        target.memory_source_ids = list(previous.memory_source_ids)
        target.memory_item_ids = list(previous.memory_item_ids)
        target.memory_excerpt_hashes = list(previous.memory_excerpt_hashes)
        target.memory_evidence_bound = previous.memory_evidence_bound
        target.memory_evidence_bound_at_utc = previous.memory_evidence_bound_at_utc
        target.memory_corrections = [dict(item) for item in previous.memory_corrections]

    @classmethod
    def _append_correction(cls, state: DialogueTaskState, user_text: str) -> None:
        semantics = analyze_memory_intent(user_text, previous_text=state.memory_query)
        raw: dict[str, Any] = {
            "text": _optional_text(user_text, limit=MAX_MEMORY_CORRECTION_TEXT) or "",
            "asserted_at_utc": _utc_now(),
        }
        if semantics.temporal_scope is not None:
            raw["temporal_scope"] = semantics.temporal_scope.to_dict()
        correction = _sanitize_correction(raw)
        if correction is not None:
            state.memory_corrections = [*state.memory_corrections, correction][-MAX_MEMORY_CORRECTIONS:]

    @classmethod
    def _suspended_anchor(cls, previous: DialogueTaskState, *, now: str) -> DialogueTaskState:
        suspended = DialogueTaskState.from_mapping(previous.to_dict())
        suspended.active = False
        suspended.execution_status = "suspended"
        suspended.memory_anchor_status = "suspended"
        suspended.expected_next_action = "return_to_memory_anchor"
        suspended.updated_at_utc = now
        suspended.turn_count += 1
        return suspended

    @classmethod
    def derive_state(
        cls,
        *,
        user_text: str,
        intent: str,
        route: str,
        previous_state: Mapping[str, Any] | DialogueTaskState | None = None,
        inherited: bool = False,
        confidence: float = 0.85,
    ) -> DialogueTaskState:
        previous = previous_state if isinstance(previous_state, DialogueTaskState) else DialogueTaskState.from_mapping(previous_state)
        now = _utc_now()
        action = cls._action_for_intent(intent, route)
        folded = _fold(user_text)
        reference_kind = (
            cls._memory_reference_kind(folded, previous_query=previous.memory_query)
            if previous.has_memory_anchor
            else None
        )

        if cls._contains_any(folded, cls._HARD_CANCEL_MARKERS):
            return DialogueTaskState(updated_at_utc=now, execution_status="cancelled")
        if cls._contains_any(folded, cls._TOPIC_SWITCH_MARKERS):
            return cls._suspended_anchor(previous, now=now) if previous.has_memory_anchor else DialogueTaskState(
                updated_at_utc=now,
                execution_status="suspended",
            )

        continuing_anchor = previous.has_memory_anchor and (
            reference_kind is not None or (inherited and _looks_like_memory_task(intent, route))
        )
        if continuing_anchor:
            copied = DialogueTaskState.from_mapping(previous.to_dict())
            copied.active = True
            copied.active_goal = _optional_text(user_text) or copied.active_goal
            copied.active_intent = intent if _looks_like_memory_task(intent, route) else copied.memory_anchor_intent
            copied.active_route = route if _looks_like_memory_task(intent, route) else copied.memory_anchor_route
            copied.execution_status = "in_progress"
            copied.expected_next_action = "recall"
            copied.memory_anchor_status = "active"
            copied.confidence = max(copied.confidence, confidence)
            copied.updated_at_utc = now
            copied.turn_count += 1
            if reference_kind == "correction":
                cls._append_correction(copied, user_text)
            return copied

        if inherited and previous.active:
            copied = DialogueTaskState.from_mapping(previous.to_dict())
            copied.active_intent = intent or copied.active_intent
            copied.active_route = route or copied.active_route
            copied.execution_status = "in_progress"
            copied.expected_next_action = action or copied.expected_next_action or "continue"
            copied.confidence = max(copied.confidence, confidence)
            copied.updated_at_utc = now
            copied.turn_count += 1
            return copied
        if not action:
            if previous.has_memory_anchor:
                if previous.active and len(folded.split()) <= 4 and cls._contains_any(folded, cls._AGREEMENT_MARKERS):
                    kept = DialogueTaskState.from_mapping(previous.to_dict())
                    kept.updated_at_utc = now
                    kept.turn_count += 1
                    return kept
                return cls._suspended_anchor(previous, now=now)
            # Keep a still-live non-memory task through a short acknowledgement,
            # but do not turn ordinary dialogue into a new task.
            if previous.active and len(folded.split()) <= 8:
                kept = DialogueTaskState.from_mapping(previous.to_dict())
                kept.updated_at_utc = now
                kept.turn_count += 1
                return kept
            return DialogueTaskState(updated_at_utc=now)
        goal = re.sub(r"\s+", " ", str(user_text or "").strip())[:320]
        topic = route or intent
        result = DialogueTaskState(
            active=True,
            task_key=_task_key(intent, route, goal),
            active_goal=goal,
            active_intent=intent,
            active_route=route,
            expected_next_action=action,
            execution_status="in_progress",
            referents=["this_task"],
            topic_stack=[topic] if topic else [],
            confidence=max(0.0, min(1.0, confidence)),
            opened_at_utc=now,
            updated_at_utc=now,
            turn_count=1,
        )
        if _looks_like_memory_task(intent, route):
            semantics = analyze_memory_intent(user_text)
            result.memory_anchor_status = "active"
            result.memory_anchor_integrity = "valid"
            result.memory_query = goal
            result.memory_query_sha256 = _text_sha256(goal)
            result.memory_anchor_goal = goal
            result.memory_anchor_intent = intent
            result.memory_anchor_route = route
            result.memory_temporal_scope = (
                _temporal_scope(semantics.temporal_scope.to_dict())
                if semantics.temporal_scope is not None
                else None
            )
            result.referents = ["this_task", "memory_anchor"]
        elif previous.has_memory_anchor:
            cls._copy_anchor(result, previous, status="suspended")
        return result

    @classmethod
    def bind_memory_evidence(
        cls,
        state: Mapping[str, Any] | DialogueTaskState | None,
        memory_payload: Mapping[str, Any] | None,
    ) -> DialogueTaskState:
        """Freeze item/source/excerpt provenance from the first grounded payload."""

        current = state if isinstance(state, DialogueTaskState) else DialogueTaskState.from_mapping(state)
        if not current.has_memory_anchor or not isinstance(memory_payload, Mapping):
            return DialogueTaskState.from_mapping(current.to_dict())
        raw_items = memory_payload.get("items")
        if isinstance(raw_items, (str, bytes, Mapping)) or not isinstance(raw_items, Iterable):
            return DialogueTaskState.from_mapping(current.to_dict())
        source_ids: list[str] = []
        item_ids: list[str] = []
        excerpt_hashes: list[str] = []
        for raw_index, raw_item in enumerate(raw_items):
            if raw_index >= MAX_MEMORY_ANCHOR_IDENTIFIERS * 2:
                break
            if not isinstance(raw_item, Mapping):
                continue
            source_id = _optional_text(
                raw_item.get("source_id") or raw_item.get("conversation_id") or raw_item.get("source"),
                limit=160,
            )
            memory_type = _optional_text(
                raw_item.get("item_type") or raw_item.get("memory_type"),
                limit=96,
            ) or "memory_item"
            timestamp = raw_item.get("timestamp")
            excerpt = _optional_text(
                raw_item.get("content_excerpt")
                or raw_item.get("excerpt")
                or raw_item.get("content")
                or raw_item.get("text"),
                limit=4000,
            )
            item_id = _optional_text(
                raw_item.get("item_id") or raw_item.get("id") or raw_item.get("message_id"),
                limit=160,
            )
            if not item_id and source_id and excerpt:
                item_id = _stable_memory_item_id(
                    memory_type=memory_type,
                    source=source_id,
                    timestamp=timestamp,
                    content=excerpt,
                )
            declared_hash = _optional_text(raw_item.get("excerpt_sha256"), limit=64)
            excerpt_hash = (
                _text_sha256(excerpt)
                if excerpt
                else (
                    declared_hash.lower()
                    if declared_hash and _SHA256_RE.fullmatch(declared_hash.lower())
                    else None
                )
            )
            # Evidence is an atomic tuple. A partial item cannot contribute a
            # source from one payload and an ID/hash from a later payload.
            if not source_id or not item_id or not excerpt_hash:
                continue
            source_ids.append(source_id)
            item_ids.append(item_id)
            excerpt_hashes.append(excerpt_hash)
            if len(item_ids) >= MAX_MEMORY_ANCHOR_IDENTIFIERS:
                break
        return current.with_memory_evidence(
            source_ids=source_ids,
            item_ids=item_ids,
            excerpt_hashes=excerpt_hashes,
        )

    def resolve(
        self,
        *,
        current_text: str,
        previous_task_state: Mapping[str, Any] | DialogueTaskState | None = None,
        previous_user_text: str | None = None,
        previous_intent: str | None = None,
        previous_route: str | None = None,
        carryover_allowed: bool = True,
        context_age_seconds: int | None = None,
    ) -> DialogueTaskResolution:
        state = previous_task_state if isinstance(previous_task_state, DialogueTaskState) else DialogueTaskState.from_mapping(previous_task_state)
        folded = _fold(current_text)
        evidence: list[str] = []
        if not carryover_allowed:
            return DialogueTaskResolution(False, evidence=["turn context resolver blocked carryover"], task_state=state)
        if context_age_seconds is not None and context_age_seconds > DEFAULT_TASK_TTL_SECONDS:
            return DialogueTaskResolution(False, evidence=["active task context expired"], task_state=state)
        if self._contains_any(folded, self._HARD_CANCEL_MARKERS):
            return DialogueTaskResolution(
                False,
                resolution_type="task_cancelled",
                evidence=["explicit hard task cancel marker"],
                task_state=DialogueTaskState(execution_status="cancelled"),
            )
        if self._contains_any(folded, self._TOPIC_SWITCH_MARKERS):
            suspended = self._suspended_anchor(state, now=_utc_now()) if state.has_memory_anchor else state
            return DialogueTaskResolution(
                False,
                resolution_type="memory_task_suspended" if state.has_memory_anchor else "topic_switched",
                evidence=["topic switch suspends the memory anchor without rewriting it"],
                task_state=suspended,
            )
        if self._contains_any(folded, self._CURRENT_TURN_SPECIAL_MARKERS):
            return DialogueTaskResolution(False, evidence=["current-turn special request overrides prior task"], task_state=state)

        reference_kind = self._memory_reference_kind(folded, previous_query=state.memory_query)
        if state.memory_anchor_status == "suspended" and reference_kind != "return":
            reference_kind = None
        if state.has_memory_anchor and reference_kind is not None:
            anchor_intent = state.memory_anchor_intent or state.active_intent
            anchor_route = state.memory_anchor_route or state.active_route
            if not anchor_intent or not anchor_route:
                return DialogueTaskResolution(
                    False,
                    resolution_type="incomplete_memory_anchor",
                    confidence=0.25,
                    evidence=["memory reference detected but the anchor lacks intent or route"],
                    task_state=state,
                    requires_clarification=True,
                )
            next_state = self.derive_state(
                user_text=current_text,
                intent=anchor_intent,
                route=anchor_route,
                previous_state=state,
                inherited=True,
                confidence=max(0.9, state.confidence),
            )
            return DialogueTaskResolution(
                True,
                resolved_intent=anchor_intent,
                resolved_route=anchor_route,
                resolution_type=f"memory_{reference_kind}_inherits_anchor",
                confidence=max(0.9, state.confidence),
                evidence=[
                    f"memory {reference_kind} reference detected",
                    "original memory query and source provenance preserved",
                    f"inherited memory anchor={state.task_key or 'unkeyed'}",
                ],
                task_state=next_state,
            )

        contextual, operation = self._looks_like_contextual_execution(folded)
        word_count = len([item for item in re.split(r"\s+", folded) if item])
        if not contextual or word_count > 28:
            return DialogueTaskResolution(False, task_state=state)

        if not state.active:
            if state.has_memory_anchor and state.memory_anchor_intent and state.memory_anchor_route:
                state = DialogueTaskState.from_mapping(state.to_dict())
                state.active = True
                state.active_intent = state.memory_anchor_intent
                state.active_route = state.memory_anchor_route
                state.memory_anchor_status = "active"
                evidence.append("suspended memory anchor reactivated for explicit continuation")
            elif previous_intent and previous_route:
                synthetic_action = self._action_for_intent(previous_intent, previous_route)
                if synthetic_action:
                    state = self.derive_state(
                        user_text=previous_user_text or previous_intent,
                        intent=previous_intent,
                        route=previous_route,
                        confidence=0.72,
                    )
                    evidence.append("active task reconstructed from previous intent/route")
            if not state.active:
                return DialogueTaskResolution(
                    False,
                    resolution_type="contextual_execution_without_task",
                    confidence=0.25,
                    evidence=["contextual execution detected but no active executable task exists"],
                    task_state=state,
                    requires_clarification=True,
                )

        if not state.active_intent or not state.active_route:
            return DialogueTaskResolution(
                False,
                resolution_type="incomplete_task_state",
                confidence=0.25,
                evidence=["active task is missing intent or route"],
                task_state=state,
                requires_clarification=True,
            )

        evidence.extend([
            f"contextual {operation} directive detected",
            "resolved against structured active task rather than a loose keyword",
            f"inherited task={state.task_key or 'unkeyed'}",
        ])
        next_state = self.derive_state(
            user_text=current_text,
            intent=state.active_intent,
            route=state.active_route,
            previous_state=state,
            inherited=True,
            confidence=max(0.88, state.confidence),
        )
        return DialogueTaskResolution(
            True,
            resolved_intent=state.active_intent,
            resolved_route=state.active_route,
            resolution_type=f"contextual_{operation}_inherits_active_task",
            confidence=max(0.88, state.confidence),
            evidence=evidence,
            task_state=next_state,
        )
