from __future__ import annotations

"""Typed conversation-turn runtime shared by MCP and ChatGPT host bridges.

This module does not own the Jaźń daemon lifecycle and does not create a second
conversation runtime. It gives transport-facing code one strict vocabulary for
route selection, request identity, phase transitions, failure observations,
retry semantics and visible-output directives.

v78 deliberately separates three axes which older host code tended to conflate:
where execution happens (``ExecutionRoute``), which host surface is asking for
it (``HostSurface``), and how a verified remote runtime is reached
(``RemoteTransport``). Availability is tri-state/four-state rather than a bool
so "not probed" can never silently become "unavailable".
"""

from dataclasses import asdict, dataclass
from enum import Enum
import hashlib
import re
from typing import Any, Mapping

from latka_jazn.version import PACKAGE_VERSION_FULL, schema_version

SCHEMA_VERSION = schema_version("professional_turn_runtime")
TURN_RUNTIME_CAPABILITY = "io.jazn/turn-runtime"
_HASH64_RE = re.compile(r"^[0-9a-f]{64}$")
_TRACE_ID_RE = re.compile(r"^[0-9a-f]{32}$")


class ExecutionRoute(str, Enum):
    REMOTE_RUNTIME = "remote_runtime"
    LOCAL_EXECUTOR = "local_executor"
    HOST_HANDOFF = "host_handoff"
    UNAVAILABLE = "unavailable"


class HostSurface(str, Enum):
    ORDINARY_CHAT = "ordinary_chat"
    CHATGPT_WORK = "chatgpt_work"
    CODEX = "codex"
    LOCAL_CLI = "local_cli"
    API = "api"
    UNKNOWN = "unknown"


class RemoteTransport(str, Enum):
    NONE = "none"
    PUBLIC_STREAMABLE_HTTP = "public_streamable_http"
    OPENAI_SECURE_MCP_TUNNEL = "openai_secure_mcp_tunnel"


class Availability(str, Enum):
    UNKNOWN = "unknown"
    AVAILABLE = "available"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


class FailureStage(str, Enum):
    PRE_SPAWN = "pre_spawn"
    POST_SPAWN = "post_spawn"
    REMOTE_CONNECT = "remote_connect"
    REMOTE_SUBMIT = "remote_submit"
    REMOTE_POLL = "remote_poll"
    AUTH = "auth"
    READY_CHECK = "ready_check"
    UNKNOWN = "unknown"


class FailureKind(str, Enum):
    TRANSPORT_TIMEOUT = "transport_timeout"
    RPC_UNAVAILABLE = "rpc_unavailable"
    GATEWAY_UNAVAILABLE = "gateway_unavailable"
    SCHEDULER_UNAVAILABLE = "scheduler_unavailable"
    QUOTA_OR_ENTITLEMENT = "quota_or_entitlement"
    RATE_LIMITED = "rate_limited"
    SPAWN_REJECTED = "spawn_rejected"
    PROCESS_STARTED_UNFINISHED = "process_started_unfinished"
    FILESYSTEM_UNAVAILABLE = "filesystem_unavailable"
    AUTHENTICATION_FAILED = "authentication_failed"
    AUTHORIZATION_FAILED = "authorization_failed"
    UNKNOWN = "unknown"


class TurnAction(str, Enum):
    DISPLAY_EXACT = "display_exact"
    GENERATE_THEN_FINALIZE = "generate_then_finalize"
    POLL_RUNTIME = "poll_runtime"
    HOST_DIAGNOSTIC = "host_diagnostic"


class TurnPhase(str, Enum):
    NEW = "new"
    SUBMITTED = "submitted"
    POLLING = "polling"
    AWAITING_HOST_FINALIZATION = "awaiting_host_finalization"
    ACCEPTED_VISIBLE = "accepted_visible"
    FAILED = "failed"


_ALLOWED_TRANSITIONS: dict[TurnPhase, frozenset[TurnPhase]] = {
    TurnPhase.NEW: frozenset({TurnPhase.SUBMITTED, TurnPhase.FAILED}),
    TurnPhase.SUBMITTED: frozenset(
        {
            TurnPhase.POLLING,
            TurnPhase.AWAITING_HOST_FINALIZATION,
            TurnPhase.ACCEPTED_VISIBLE,
            TurnPhase.FAILED,
        }
    ),
    TurnPhase.POLLING: frozenset(
        {
            TurnPhase.POLLING,
            TurnPhase.AWAITING_HOST_FINALIZATION,
            TurnPhase.ACCEPTED_VISIBLE,
            TurnPhase.FAILED,
        }
    ),
    TurnPhase.AWAITING_HOST_FINALIZATION: frozenset(
        {TurnPhase.ACCEPTED_VISIBLE, TurnPhase.FAILED}
    ),
    TurnPhase.ACCEPTED_VISIBLE: frozenset(),
    TurnPhase.FAILED: frozenset(),
}


class TurnProtocolViolation(ValueError):
    """Raised when a transport result would weaken the canonical turn contract."""


@dataclass(frozen=True, slots=True)
class FailureObservation:
    """What was actually observed, without upgrading hypotheses to root causes."""

    observed_error_code: str
    stage: FailureStage
    confirmed_kind: FailureKind = FailureKind.UNKNOWN
    root_cause_confirmed: bool = False
    candidate_domains: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["stage"] = self.stage.value
        payload["confirmed_kind"] = self.confirmed_kind.value
        return payload

    @classmethod
    def from_error(
        cls,
        error_code: str,
        *,
        stage: FailureStage = FailureStage.UNKNOWN,
    ) -> "FailureObservation":
        code = str(error_code or "").strip() or "UnknownError"
        normalized = code.lower()

        if "transporttimeouterror" in normalized or normalized == "transport_timeout":
            if stage is FailureStage.PRE_SPAWN:
                return cls(
                    observed_error_code=code,
                    stage=stage,
                    confirmed_kind=FailureKind.UNKNOWN,
                    root_cause_confirmed=False,
                    candidate_domains=(
                        "host_rpc",
                        "gateway",
                        "runtime_provisioning",
                        "scheduler",
                        "quota_or_entitlement",
                    ),
                )
            return cls(
                observed_error_code=code,
                stage=stage,
                confirmed_kind=FailureKind.TRANSPORT_TIMEOUT,
                root_cause_confirmed=False,
                candidate_domains=("transport", "gateway", "remote_runtime"),
            )

        if normalized in {"401", "http_401", "authentication_failed"}:
            return cls(code, stage, FailureKind.AUTHENTICATION_FAILED, True, ("authentication",))
        if normalized in {"403", "http_403", "authorization_failed"}:
            return cls(code, stage, FailureKind.AUTHORIZATION_FAILED, True, ("authorization", "entitlement"))
        if normalized in {"429", "http_429", "rate_limited"}:
            return cls(code, stage, FailureKind.RATE_LIMITED, True, ("rate_limit",))

        return cls(
            observed_error_code=code,
            stage=stage,
            confirmed_kind=FailureKind.UNKNOWN,
            root_cause_confirmed=False,
        )


@dataclass(frozen=True, slots=True)
class TurnIdentity:
    request_id: str
    session_id: str | None
    message_sha256: str
    transport_trace_id: str
    transport_span_id: str

    @classmethod
    def build(
        cls,
        *,
        request_id: str,
        message: str = "",
        session_id: str | None = None,
    ) -> "TurnIdentity":
        normalized = str(request_id or "").strip()
        if not normalized:
            raise TurnProtocolViolation("request_id_required")
        if len(normalized) > 256:
            raise TurnProtocolViolation("request_id_too_large")
        normalized_session = str(session_id or "").strip() or None
        if normalized_session is not None and len(normalized_session) > 128:
            raise TurnProtocolViolation("session_id_too_large")
        message_digest = hashlib.sha256(str(message).encode("utf-8")).hexdigest()
        trace_material = b"jazn-turn-runtime-v1\0" + normalized.encode("utf-8")
        trace_id = hashlib.sha256(trace_material).hexdigest()[:32]
        span_material = (trace_id + "\0" + message_digest).encode("ascii")
        span_id = hashlib.sha256(span_material).hexdigest()[:16]
        return cls(
            request_id=normalized,
            session_id=normalized_session,
            message_sha256=message_digest,
            transport_trace_id=trace_id,
            transport_span_id=span_id,
        )

    @property
    def traceparent(self) -> str:
        # W3C Trace Context v00 wire shape. No user text or PII is embedded.
        return f"00-{self.transport_trace_id}-{self.transport_span_id}-01"

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["traceparent"] = self.traceparent
        return payload


@dataclass(frozen=True, slots=True)
class RouteEvidence:
    host_surface: HostSurface = HostSurface.UNKNOWN

    local_executor_state: Availability = Availability.UNKNOWN
    local_executor_capability_explicit: bool = False
    local_executor_breaker_open: bool = False

    remote_transport: RemoteTransport = RemoteTransport.NONE
    remote_endpoint_configured: bool = False
    remote_auth_ready: bool = False
    remote_protocol_compatible: bool = False

    remote_process_running: bool = False
    remote_healthy: bool = False
    remote_ready: bool = False

    host_connector_capability_available: bool = False
    host_handoff_available: bool = False

    @property
    def verified_remote_runtime(self) -> bool:
        return bool(
            self.remote_transport is not RemoteTransport.NONE
            and self.remote_endpoint_configured
            and self.remote_auth_ready
            and self.remote_protocol_compatible
            and self.remote_process_running
            and self.remote_healthy
            and self.remote_ready
            and self.host_connector_capability_available
        )

    @property
    def verified_local_executor(self) -> bool:
        if self.local_executor_state is not Availability.AVAILABLE:
            return False
        if self.local_executor_breaker_open:
            return False
        if self.host_surface is HostSurface.ORDINARY_CHAT:
            return self.local_executor_capability_explicit
        return True


@dataclass(frozen=True, slots=True)
class RouteDecision:
    execution_route: ExecutionRoute
    reason_code: str
    remote_runtime_verified: bool
    local_executor_available: bool
    host_handoff_available: bool
    host_surface: HostSurface = HostSurface.UNKNOWN
    remote_transport: RemoteTransport = RemoteTransport.NONE

    @property
    def executable(self) -> bool:
        return self.execution_route is not ExecutionRoute.UNAVAILABLE

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["execution_route"] = self.execution_route.value
        payload["host_surface"] = self.host_surface.value
        payload["remote_transport"] = self.remote_transport.value
        payload["executable"] = self.executable
        return payload


@dataclass(frozen=True, slots=True)
class TurnDirective:
    action: TurnAction
    phase: TurnPhase
    request_id: str
    turn_id: str | None = None
    trace_id: str | None = None
    visible_text: str | None = None
    continuation_token: str | None = None
    host_request_contract_hash: str | None = None
    diagnostic_reason: str | None = None
    must_not_resubmit_user_message: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["action"] = self.action.value
        payload["phase"] = self.phase.value
        return payload


class ProfessionalTurnRuntime:
    """One strict transport policy around the existing Jaźń runtime.

    The class is intentionally model-agnostic. LLM generation remains behind
    Jaźń's existing engine/model adapters while this layer keeps host transport
    semantics deterministic and fail-closed.
    """

    @staticmethod
    def choose_route(evidence: RouteEvidence) -> RouteDecision:
        if evidence.verified_remote_runtime:
            return RouteDecision(
                execution_route=ExecutionRoute.REMOTE_RUNTIME,
                reason_code="verified_remote_runtime_preferred",
                remote_runtime_verified=True,
                local_executor_available=evidence.verified_local_executor,
                host_handoff_available=evidence.host_handoff_available,
                host_surface=evidence.host_surface,
                remote_transport=evidence.remote_transport,
            )
        if evidence.verified_local_executor:
            return RouteDecision(
                execution_route=ExecutionRoute.LOCAL_EXECUTOR,
                reason_code="verified_local_executor_remote_unavailable",
                remote_runtime_verified=False,
                local_executor_available=True,
                host_handoff_available=evidence.host_handoff_available,
                host_surface=evidence.host_surface,
                remote_transport=evidence.remote_transport,
            )
        if evidence.host_handoff_available:
            return RouteDecision(
                execution_route=ExecutionRoute.HOST_HANDOFF,
                reason_code="verified_routes_unavailable_host_handoff_available",
                remote_runtime_verified=False,
                local_executor_available=False,
                host_handoff_available=True,
                host_surface=evidence.host_surface,
                remote_transport=evidence.remote_transport,
            )
        return RouteDecision(
            execution_route=ExecutionRoute.UNAVAILABLE,
            reason_code="no_verified_execution_route",
            remote_runtime_verified=False,
            local_executor_available=False,
            host_handoff_available=False,
            host_surface=evidence.host_surface,
            remote_transport=evidence.remote_transport,
        )

    @staticmethod
    def transition_allowed(current: TurnPhase, target: TurnPhase) -> bool:
        return target in _ALLOWED_TRANSITIONS[current]

    @staticmethod
    def require_transition(current: TurnPhase, target: TurnPhase) -> None:
        if not ProfessionalTurnRuntime.transition_allowed(current, target):
            raise TurnProtocolViolation(
                f"illegal_turn_transition:{current.value}->{target.value}"
            )

    @staticmethod
    def retry_semantics(tool_name: str, *, action: str | None = None) -> dict[str, Any]:
        name = str(tool_name or "").strip()
        normalized_action = str(action or "").strip()
        if name == "jazn_generate_visible_reply":
            return {
                "automatic_retry_allowed": False,
                "resume_same_request_id": True,
                "replay_user_message_allowed": False,
                "reason": "side_effecting_turn_submission_requires_idempotent_request_identity",
            }
        if name in {"jazn_resume_visible_reply", "jazn_status", "jazn_audit_lookup"}:
            return {
                "automatic_retry_allowed": True,
                "resume_same_request_id": normalized_action == TurnAction.POLL_RUNTIME.value,
                "replay_user_message_allowed": False,
                "reason": "read_or_resume_operation",
            }
        return {
            "automatic_retry_allowed": False,
            "resume_same_request_id": False,
            "replay_user_message_allowed": False,
            "reason": "explicit_host_decision_required",
        }

    @staticmethod
    def _structured(result: Mapping[str, Any]) -> Mapping[str, Any]:
        value = result.get("structuredContent")
        return value if isinstance(value, Mapping) else {}

    @staticmethod
    def _request_id_from(structured: Mapping[str, Any]) -> str:
        return str(
            structured.get("daemon_request_id")
            or structured.get("request_id")
            or ""
        ).strip()

    @staticmethod
    def _require_same_request_id(
        structured: Mapping[str, Any],
        identity: TurnIdentity,
        *,
        required: bool,
    ) -> None:
        observed = ProfessionalTurnRuntime._request_id_from(structured)
        if not observed:
            if required:
                raise TurnProtocolViolation("daemon_request_id_missing")
            return
        if observed != identity.request_id:
            raise TurnProtocolViolation("daemon_request_id_mismatch")

    @staticmethod
    def _action(result: Mapping[str, Any]) -> TurnAction:
        structured = ProfessionalTurnRuntime._structured(result)
        raw = str(structured.get("action") or "").strip()
        if not raw and result.get("isError") is True:
            raw = TurnAction.HOST_DIAGNOSTIC.value
        try:
            return TurnAction(raw)
        except ValueError as exc:
            raise TurnProtocolViolation(f"unsupported_turn_action:{raw or 'missing'}") from exc

    def classify_tool_result(
        self,
        *,
        tool_name: str,
        result: Mapping[str, Any],
        identity: TurnIdentity,
    ) -> TurnDirective:
        structured = self._structured(result)
        action = self._action(result)
        turn_id = str(structured.get("turn_id") or "").strip() or None
        trace_id = str(structured.get("trace_id") or "").strip() or None

        if action is TurnAction.HOST_DIAGNOSTIC:
            reason = str(structured.get("reason") or "runtime_host_diagnostic_required")
            return TurnDirective(
                action=action,
                phase=TurnPhase.FAILED,
                request_id=identity.request_id,
                turn_id=turn_id,
                trace_id=trace_id,
                diagnostic_reason=reason,
            )

        if action is TurnAction.POLL_RUNTIME:
            self._require_same_request_id(structured, identity, required=True)
            if structured.get("must_not_resubmit_user_message") is not True:
                raise TurnProtocolViolation("poll_runtime_replay_guard_missing")
            return TurnDirective(
                action=action,
                phase=TurnPhase.POLLING,
                request_id=identity.request_id,
                turn_id=turn_id,
                trace_id=trace_id,
                must_not_resubmit_user_message=True,
            )

        if action is TurnAction.GENERATE_THEN_FINALIZE:
            self._require_same_request_id(structured, identity, required=False)
            token = str(structured.get("continuation_token") or "").strip()
            contract_hash = str(
                structured.get("host_request_contract_hash") or ""
            ).strip().lower()
            if not token:
                raise TurnProtocolViolation("continuation_token_missing")
            if not _HASH64_RE.fullmatch(contract_hash):
                raise TurnProtocolViolation("host_request_contract_hash_invalid")
            if str(structured.get("finalization_tool") or "") != "jazn_finalize_reply":
                raise TurnProtocolViolation("finalization_tool_invalid")
            if structured.get("must_not_display_intermediate") is not True:
                raise TurnProtocolViolation("intermediate_display_guard_missing")
            return TurnDirective(
                action=action,
                phase=TurnPhase.AWAITING_HOST_FINALIZATION,
                request_id=identity.request_id,
                turn_id=turn_id,
                trace_id=trace_id,
                continuation_token=token,
                host_request_contract_hash=contract_hash,
            )

        if action is TurnAction.DISPLAY_EXACT:
            final_text = str(structured.get("final_visible_text") or "")
            if not final_text:
                raise TurnProtocolViolation("final_visible_text_missing")
            if structured.get("must_display_exactly") is not True:
                raise TurnProtocolViolation("display_exact_guard_missing")
            return TurnDirective(
                action=action,
                phase=TurnPhase.ACCEPTED_VISIBLE,
                request_id=identity.request_id,
                turn_id=turn_id,
                trace_id=trace_id,
                visible_text=final_text,
            )

        raise TurnProtocolViolation("unreachable_turn_action")

    def decorate_tool_result(
        self,
        *,
        tool_name: str,
        result: Mapping[str, Any],
        identity: TurnIdentity,
    ) -> dict[str, Any]:
        directive = self.classify_tool_result(
            tool_name=tool_name,
            result=result,
            identity=identity,
        )
        value = dict(result)
        metadata = dict(value.get("_meta") or {})
        metadata[TURN_RUNTIME_CAPABILITY] = {
            "schema_version": SCHEMA_VERSION,
            "package_version": PACKAGE_VERSION_FULL,
            "identity": identity.to_dict(),
            "directive": directive.to_dict(),
            "retry": self.retry_semantics(tool_name, action=directive.action.value),
        }
        value["_meta"] = metadata
        return value

    @staticmethod
    def fail_closed_tool_result(
        reason: str,
        *,
        identity: TurnIdentity | None = None,
    ) -> dict[str, Any]:
        structured: dict[str, Any] = {
            "ok": False,
            "action": TurnAction.HOST_DIAGNOSTIC.value,
            "reason": f"turn_runtime_protocol_violation:{reason}",
            "visible_output_source": "host_diagnostic",
        }
        metadata: dict[str, Any] = {
            TURN_RUNTIME_CAPABILITY: {
                "schema_version": SCHEMA_VERSION,
                "package_version": PACKAGE_VERSION_FULL,
                "fail_closed": True,
                "reason": reason,
            }
        }
        if identity is not None:
            metadata[TURN_RUNTIME_CAPABILITY]["identity"] = identity.to_dict()
        return {
            "content": [
                {
                    "type": "text",
                    "text": "Jaźń turn runtime rejected an inconsistent transport result.",
                }
            ],
            "structuredContent": structured,
            "_meta": metadata,
            "isError": True,
        }

    @staticmethod
    def capability_descriptor() -> dict[str, Any]:
        return {
            "schemaVersion": SCHEMA_VERSION,
            "packageVersion": PACKAGE_VERSION_FULL,
            "stableRequestIdentity": True,
            "remoteRuntimePreferredWhenVerified": True,
            "availabilitySemantics": "tri_state_plus_degraded",
            "ordinaryChatBlindLocalProbe": False,
            "transportAmbiguityRecovery": "resume_same_request_id_never_replay",
            "visibleOutputGate": "display_exact_after_runtime_or_host_finalization",
            "traceContext": "w3c-traceparent-compatible-transport-correlation",
            "standardMcpTasksClaimed": False,
        }


def valid_w3c_trace_id(value: str) -> bool:
    normalized = str(value or "").strip().lower()
    return bool(_TRACE_ID_RE.fullmatch(normalized) and normalized != "0" * 32)


__all__ = [
    "Availability",
    "ExecutionRoute",
    "FailureKind",
    "FailureObservation",
    "FailureStage",
    "HostSurface",
    "ProfessionalTurnRuntime",
    "RemoteTransport",
    "RouteDecision",
    "RouteEvidence",
    "SCHEMA_VERSION",
    "TURN_RUNTIME_CAPABILITY",
    "TurnAction",
    "TurnDirective",
    "TurnIdentity",
    "TurnPhase",
    "TurnProtocolViolation",
    "valid_w3c_trace_id",
]
