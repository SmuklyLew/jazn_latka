from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import hashlib
from typing import Any, Iterable, Mapping


SCHEMA_VERSION = "turn_diagnostic_trace/v1"

_SENSITIVE_KEY_FRAGMENTS = (
    "authorization",
    "password",
    "secret",
    "token",
    "prompt",
    "raw_text",
    "user_text",
    "assistant_text",
    "memory_excerpt",
    "journal",
    "body",
    "content",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _enum_value(value: Any) -> str:
    if isinstance(value, Enum):
        return str(value.value)
    return str(value)


def _is_sensitive_key(key: str) -> bool:
    normalized = str(key or "").strip().lower()
    return any(fragment in normalized for fragment in _SENSITIVE_KEY_FRAGMENTS)


def _sanitize_value(value: Any, *, key: str = "", depth: int = 0) -> Any:
    if _is_sensitive_key(key):
        return "<redacted>"
    if depth >= 4:
        return "<max_depth>"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, str):
        if len(value) > 512:
            return value[:509] + "..."
        return value
    if isinstance(value, Mapping):
        return {
            str(item_key): _sanitize_value(
                item_value,
                key=str(item_key),
                depth=depth + 1,
            )
            for item_key, item_value in value.items()
        }
    if isinstance(value, (list, tuple, set, frozenset)):
        return [
            _sanitize_value(item, depth=depth + 1)
            for item in list(value)[:64]
        ]
    return f"<{type(value).__name__}>"


class TurnStage(str, Enum):
    INGRESS = "INGRESS"
    TURN_BINDING = "TURN_BINDING"
    CONTEXT = "CONTEXT"
    MEMORY = "MEMORY"
    COGNITION = "COGNITION"
    AFFECT = "AFFECT"
    ROUTING = "ROUTING"
    HANDLER = "HANDLER"
    MODEL = "MODEL"
    TOOL = "TOOL"
    VALIDATION = "VALIDATION"
    RECOVERY = "RECOVERY"
    FINALIZATION = "FINALIZATION"
    PERSISTENCE = "PERSISTENCE"
    PRESENTATION = "PRESENTATION"
    SETTLEMENT = "SETTLEMENT"


class FailureKind(str, Enum):
    INVALID_INPUT = "INVALID_INPUT"
    CAPABILITY_UNAVAILABLE = "CAPABILITY_UNAVAILABLE"
    DEPENDENCY_NOT_READY = "DEPENDENCY_NOT_READY"
    TIMEOUT = "TIMEOUT"
    CANCELLED = "CANCELLED"
    CONTRACT_VIOLATION = "CONTRACT_VIOLATION"
    LINEAGE_MISMATCH = "LINEAGE_MISMATCH"
    ROUTE_UNRESOLVED = "ROUTE_UNRESOLVED"
    HANDLER_EXCEPTION = "HANDLER_EXCEPTION"
    REQUIRED_COMPONENT_MISSING = "REQUIRED_COMPONENT_MISSING"
    MEMORY_EVIDENCE_UNAVAILABLE = "MEMORY_EVIDENCE_UNAVAILABLE"
    MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"
    TOOL_UNAVAILABLE = "TOOL_UNAVAILABLE"
    VALIDATION_REJECTED = "VALIDATION_REJECTED"
    FINALIZATION_REJECTED = "FINALIZATION_REJECTED"
    PERSISTENCE_FAILED = "PERSISTENCE_FAILED"
    DUPLICATE_ACCEPTED_FINAL = "DUPLICATE_ACCEPTED_FINAL"
    INTERNAL_INVARIANT_BROKEN = "INTERNAL_INVARIANT_BROKEN"


class FallbackKind(str, Enum):
    RECOVERABLE_FALLBACK = "RECOVERABLE_FALLBACK"
    EXTERNAL_CAPABILITY_REQUIRED = "EXTERNAL_CAPABILITY_REQUIRED"
    TERMINAL_DIAGNOSTIC = "TERMINAL_DIAGNOSTIC"


class DiagnosticSeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


@dataclass(frozen=True, slots=True)
class DiagnosticEvent:
    seq: int
    timestamp_utc: str
    stage: str
    component: str
    event_type: str
    outcome: str
    reason_code: str | None = None
    severity: str = DiagnosticSeverity.INFO.value
    attributes: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "seq": self.seq,
            "timestamp_utc": self.timestamp_utc,
            "stage": self.stage,
            "component": self.component,
            "event_type": self.event_type,
            "outcome": self.outcome,
            "reason_code": self.reason_code,
            "severity": self.severity,
            "attributes": _sanitize_value(self.attributes),
        }


@dataclass(frozen=True, slots=True)
class FallbackDecision:
    kind: str
    origin_stage: str
    origin_component: str
    reason_code: str
    from_route: str | None = None
    to_route: str | None = None
    recoverable: bool = False
    required_capability: str | None = None
    attempt: int = 0
    evidence_refs: tuple[str, ...] = ()

    @classmethod
    def build(
        cls,
        *,
        kind: FallbackKind | str,
        origin_stage: TurnStage | str,
        origin_component: str,
        reason_code: str,
        from_route: str | None = None,
        to_route: str | None = None,
        recoverable: bool,
        required_capability: str | None = None,
        attempt: int = 0,
        evidence_refs: Iterable[str] = (),
    ) -> "FallbackDecision":
        return cls(
            kind=_enum_value(kind),
            origin_stage=_enum_value(origin_stage),
            origin_component=str(origin_component),
            reason_code=str(reason_code),
            from_route=str(from_route) if from_route is not None else None,
            to_route=str(to_route) if to_route is not None else None,
            recoverable=bool(recoverable),
            required_capability=(
                str(required_capability) if required_capability is not None else None
            ),
            attempt=max(0, int(attempt)),
            evidence_refs=tuple(str(item) for item in evidence_refs if str(item).strip()),
        )

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "FallbackDecision":
        data = dict(payload or {})
        return cls.build(
            kind=str(data.get("kind") or FallbackKind.RECOVERABLE_FALLBACK.value),
            origin_stage=str(data.get("origin_stage") or TurnStage.RECOVERY.value),
            origin_component=str(data.get("origin_component") or "unknown"),
            reason_code=str(data.get("reason_code") or "UNSPECIFIED_FALLBACK"),
            from_route=(
                str(data.get("from_route"))
                if data.get("from_route") is not None
                else None
            ),
            to_route=(
                str(data.get("to_route"))
                if data.get("to_route") is not None
                else None
            ),
            recoverable=bool(data.get("recoverable")),
            required_capability=(
                str(data.get("required_capability"))
                if data.get("required_capability") is not None
                else None
            ),
            attempt=int(data.get("attempt") or 0),
            evidence_refs=tuple(
                str(item)
                for item in data.get("evidence_refs") or ()
                if str(item).strip()
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "origin_stage": self.origin_stage,
            "origin_component": self.origin_component,
            "reason_code": self.reason_code,
            "from_route": self.from_route,
            "to_route": self.to_route,
            "recoverable": self.recoverable,
            "required_capability": self.required_capability,
            "attempt": self.attempt,
            "evidence_refs": list(self.evidence_refs),
        }


@dataclass(frozen=True, slots=True)
class BlindRouteFinding:
    code: str
    stage: str
    component: str
    severity: str
    attributes: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def build(
        cls,
        *,
        code: str,
        stage: TurnStage | str,
        component: str,
        severity: DiagnosticSeverity | str = DiagnosticSeverity.ERROR,
        attributes: Mapping[str, Any] | None = None,
    ) -> "BlindRouteFinding":
        return cls(
            code=str(code),
            stage=_enum_value(stage),
            component=str(component),
            severity=_enum_value(severity),
            attributes=dict(_sanitize_value(dict(attributes or {}))),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "stage": self.stage,
            "component": self.component,
            "severity": self.severity,
            "attributes": _sanitize_value(self.attributes),
        }


@dataclass(slots=True)
class TurnDiagnosticTrace:
    session_id: str
    request_id: str
    turn_id: str
    trace_id: str
    revision: int = 0
    schema_version: str = SCHEMA_VERSION
    events: list[DiagnosticEvent] = field(default_factory=list)
    blind_route_findings: list[BlindRouteFinding] = field(default_factory=list)
    selected_intent: str | None = None
    selected_route: str | None = None
    selected_handler: str | None = None
    fallback: FallbackDecision | None = None
    fallback_history: list[FallbackDecision] = field(default_factory=list)
    final_outcome: str | None = None
    failure_kind: str | None = None
    failure_reason_code: str | None = None
    failure_signature: str | None = None
    _next_seq: int = field(default=1, init=False, repr=False)
    diagnostic_id: str = field(default="", init=False)

    def __post_init__(self) -> None:
        digest = hashlib.sha256(
            f"{self.trace_id}:{self.turn_id}".encode("utf-8")
        ).hexdigest()[:16].upper()
        self.diagnostic_id = f"JAZN-TURN-{digest}"

    @classmethod
    def create(
        cls,
        *,
        session_id: str,
        request_id: str,
        turn_id: str,
        trace_id: str,
    ) -> "TurnDiagnosticTrace":
        return cls(
            session_id=str(session_id),
            request_id=str(request_id),
            turn_id=str(turn_id),
            trace_id=str(trace_id),
        )

    def record_event(
        self,
        *,
        stage: TurnStage | str,
        component: str,
        event_type: str,
        outcome: str,
        reason_code: str | None = None,
        severity: DiagnosticSeverity | str = DiagnosticSeverity.INFO,
        attributes: Mapping[str, Any] | None = None,
    ) -> DiagnosticEvent:
        event = DiagnosticEvent(
            seq=self._next_seq,
            timestamp_utc=_utc_now(),
            stage=_enum_value(stage),
            component=str(component),
            event_type=str(event_type),
            outcome=str(outcome),
            reason_code=str(reason_code) if reason_code is not None else None,
            severity=_enum_value(severity),
            attributes=dict(_sanitize_value(dict(attributes or {}))),
        )
        self._next_seq += 1
        self.events.append(event)
        return event

    def bind_route(
        self,
        *,
        intent: str | None,
        route: str | None,
        handler: str | None,
        attributes: Mapping[str, Any] | None = None,
    ) -> None:
        self.selected_intent = str(intent) if intent is not None else None
        self.selected_route = str(route) if route is not None else None
        self.selected_handler = str(handler) if handler is not None else None
        self.record_event(
            stage=TurnStage.ROUTING,
            component="RouteRegistry",
            event_type="route_bound",
            outcome="selected",
            attributes={
                "intent": self.selected_intent,
                "route": self.selected_route,
                "handler": self.selected_handler,
                **dict(attributes or {}),
            },
        )

    def _signature(
        self,
        *,
        stage: TurnStage | str,
        component: str,
        reason_code: str,
        validator_code: str | None = None,
    ) -> str:
        payload = "|".join(
            [
                _enum_value(stage),
                str(component),
                str(reason_code),
                str(self.selected_route or ""),
                str(self.selected_handler or ""),
                str(validator_code or ""),
            ]
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]

    def record_failure(
        self,
        *,
        kind: FailureKind | str,
        stage: TurnStage | str,
        component: str,
        reason_code: str,
        validator_code: str | None = None,
        attributes: Mapping[str, Any] | None = None,
    ) -> None:
        self.failure_kind = _enum_value(kind)
        self.failure_reason_code = str(reason_code)
        self.failure_signature = self._signature(
            stage=stage,
            component=component,
            reason_code=reason_code,
            validator_code=validator_code,
        )
        self.record_event(
            stage=stage,
            component=component,
            event_type="failure",
            outcome="failed",
            reason_code=reason_code,
            severity=DiagnosticSeverity.ERROR,
            attributes={
                "failure_kind": self.failure_kind,
                "failure_signature": self.failure_signature,
                "validator_code": validator_code,
                **dict(attributes or {}),
            },
        )

    def record_fallback(self, decision: FallbackDecision) -> None:
        self.fallback = decision
        self.fallback_history.append(decision)
        self.record_event(
            stage=decision.origin_stage,
            component=decision.origin_component,
            event_type="fallback",
            outcome=decision.kind,
            reason_code=decision.reason_code,
            severity=(
                DiagnosticSeverity.ERROR
                if decision.kind == FallbackKind.TERMINAL_DIAGNOSTIC.value
                else DiagnosticSeverity.WARNING
            ),
            attributes=decision.to_dict(),
        )

    def add_findings(self, findings: Iterable[BlindRouteFinding]) -> None:
        for finding in findings:
            self.blind_route_findings.append(finding)
            self.record_event(
                stage=finding.stage,
                component=finding.component,
                event_type="blind_route_finding",
                outcome="detected",
                reason_code=finding.code,
                severity=finding.severity,
                attributes=finding.attributes,
            )

    def finalize(
        self,
        *,
        outcome: str,
        failure_kind: FailureKind | str | None = None,
        reason_code: str | None = None,
        component: str = "TurnDiagnosticTrace",
    ) -> None:
        resolved_outcome = str(outcome)
        if self.final_outcome is not None:
            if self.final_outcome == resolved_outcome:
                return
            raise RuntimeError(
                "turn_diagnostic_final_outcome_already_set:"
                f"{self.final_outcome}->{resolved_outcome}"
            )
        self.final_outcome = resolved_outcome
        if failure_kind is not None and reason_code:
            self.record_failure(
                kind=failure_kind,
                stage=TurnStage.SETTLEMENT,
                component=component,
                reason_code=reason_code,
            )
        self.record_event(
            stage=TurnStage.SETTLEMENT,
            component=component,
            event_type="turn_finalized",
            outcome=self.final_outcome,
            reason_code=reason_code,
            severity=(
                DiagnosticSeverity.ERROR
                if self.final_outcome in {"failed", "rejected", "terminal"}
                else DiagnosticSeverity.INFO
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "diagnostic_id": self.diagnostic_id,
            "session_id": self.session_id,
            "request_id": self.request_id,
            "turn_id": self.turn_id,
            "trace_id": self.trace_id,
            "revision": self.revision,
            "selected_intent": self.selected_intent,
            "selected_route": self.selected_route,
            "selected_handler": self.selected_handler,
            "fallback": self.fallback.to_dict() if self.fallback else None,
            "fallback_history": [
                item.to_dict() for item in self.fallback_history
            ],
            "blind_route_findings": [
                finding.to_dict() for finding in self.blind_route_findings
            ],
            "final_outcome": self.final_outcome,
            "failure_kind": self.failure_kind,
            "failure_reason_code": self.failure_reason_code,
            "failure_signature": self.failure_signature,
            "event_count": len(self.events),
            "events": [event.to_dict() for event in self.events],
            "privacy_boundary": (
                "Operational diagnostics only. Raw user text, prompts, memory excerpts, "
                "journal content and secrets are redacted/not collected by this contract."
            ),
        }
