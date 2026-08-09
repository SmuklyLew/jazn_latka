from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import hashlib
import re
import unicodedata
from typing import Any, Mapping

from latka_jazn.version import schema_version

SCHEMA_VERSION = schema_version("dialogue_task_state")
DEFAULT_TASK_TTL_SECONDS = 21600

_DIACRITIC_MAP = str.maketrans("ąćęłńóśźżĄĆĘŁŃÓŚŹŻ", "acelnoszzACELNOSZZ")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", str(text or "")).strip().lower())


def _fold(text: str) -> str:
    return _normalize(text).translate(_DIACRITIC_MAP)


def _task_key(intent: str, route: str, goal: str) -> str:
    material = f"{intent}\n{route}\n{_fold(goal)[:320]}".encode("utf-8")
    return hashlib.sha256(material).hexdigest()[:24]


@dataclass(slots=True)
class DialogueTaskState:
    """Small durable representation of the user's active conversational task.

    This is not a transcript and not a memory record.  It is deliberately a
    compact execution/navigation state used to resolve references such as
    ``zrób to`` or ``kontynuuj`` without reclassifying every turn from scratch.
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
    schema_version: str = SCHEMA_VERSION
    truth_boundary: str = (
        "Stan zadania opisuje wyłącznie aktywny cel rozmowy i oczekiwaną akcję. "
        "Nie jest autobiograficznym wspomnieniem, przeżyciem ani dowodem wykonania zadania."
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any] | None) -> "DialogueTaskState":
        if not isinstance(value, Mapping):
            return cls()
        referents = [str(item) for item in value.get("referents", []) if str(item).strip()][:8]
        topic_stack = [str(item) for item in value.get("topic_stack", []) if str(item).strip()][:8]
        return cls(
            active=bool(value.get("active")),
            task_key=str(value.get("task_key") or "").strip() or None,
            active_goal=str(value.get("active_goal") or "").strip() or None,
            active_intent=str(value.get("active_intent") or "").strip() or None,
            active_route=str(value.get("active_route") or "").strip() or None,
            expected_next_action=str(value.get("expected_next_action") or "").strip() or None,
            execution_status=str(value.get("execution_status") or "idle").strip() or "idle",
            referents=referents,
            topic_stack=topic_stack,
            confidence=max(0.0, min(1.0, float(value.get("confidence") or 0.0))),
            opened_at_utc=str(value.get("opened_at_utc") or "").strip() or None,
            updated_at_utc=str(value.get("updated_at_utc") or "").strip() or None,
            turn_count=max(0, int(value.get("turn_count") or 0)),
            source=str(value.get("source") or "runtime_dialogue"),
            schema_version=str(value.get("schema_version") or SCHEMA_VERSION),
            truth_boundary=str(value.get("truth_boundary") or cls().truth_boundary),
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
        "Dziedziczenie celu jest dozwolone tylko dla krótkiej, jawnej kontynuacji zgodnej z aktywnym zadaniem. "
        "Nowa treść użytkownika zawsze ma pierwszeństwo przed starym stanem."
    )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        return payload


class DialogueTaskStateResolver:
    """Resolve conversational execution references against a structured task state."""

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
    _RESET_MARKERS = (
        "zmienmy temat", "nowy temat", "inna sprawa", "zostaw to", "nie rob tego",
        "anuluj", "stop", "przestan", "zapomnij o tym",
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
    def _action_for_intent(cls, intent: str, route: str) -> str | None:
        intent_folded = _fold(intent)
        route_folded = _fold(route)
        if "recall" in intent_folded or "memory" in route_folded:
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
        if cls._contains_any(folded, cls._RESET_MARKERS):
            return DialogueTaskState(updated_at_utc=now, execution_status="cancelled")
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
            # Keep a still-live task through conversational acknowledgement, but do
            # not turn ordinary dialogue into a new task.
            if previous.active and len(folded.split()) <= 8 and not cls._contains_any(folded, cls._RESET_MARKERS):
                kept = DialogueTaskState.from_mapping(previous.to_dict())
                kept.updated_at_utc = now
                kept.turn_count += 1
                return kept
            return DialogueTaskState(updated_at_utc=now)
        goal = re.sub(r"\s+", " ", str(user_text or "").strip())[:320]
        topic = route or intent
        return DialogueTaskState(
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
        if self._contains_any(folded, self._RESET_MARKERS):
            return DialogueTaskResolution(False, resolution_type="task_cancelled", evidence=["explicit task reset/cancel marker"], task_state=DialogueTaskState(execution_status="cancelled"))
        if self._contains_any(folded, self._CURRENT_TURN_SPECIAL_MARKERS):
            return DialogueTaskResolution(False, evidence=["current-turn special request overrides prior task"], task_state=state)

        contextual, operation = self._looks_like_contextual_execution(folded)
        word_count = len([item for item in re.split(r"\s+", folded) if item])
        if not contextual or word_count > 28:
            return DialogueTaskResolution(False, task_state=state)

        if not state.active:
            if previous_intent and previous_route:
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
