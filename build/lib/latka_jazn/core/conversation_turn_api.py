from __future__ import annotations

"""Canonical turn operations; durable jobs and acceptance stay in existing stores."""

from dataclasses import dataclass, field
from typing import Any, Protocol, TYPE_CHECKING
import uuid
from latka_jazn.core.json_types import json_object

from latka_jazn.runtime.turn_runtime import ProfessionalTurnRuntime, TurnPhase, TurnProtocolViolation

if TYPE_CHECKING:
    from latka_jazn.config import JaznConfig
    from latka_jazn.core.host_finalization_transaction import HostFinalizationPorts


@dataclass(frozen=True)
class TurnRequest:
    text: str
    request_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    session_id: str | None = None
    options: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TurnHandle:
    request_id: str
    session_id: str | None = None


@dataclass(frozen=True)
class ResumeRequest:
    handle: TurnHandle


@dataclass(frozen=True)
class FinalizeRequest:
    handle: TurnHandle
    config: JaznConfig
    payload: dict[str, Any]
    chat_bridge_meta: dict[str, Any]
    contract: dict[str, Any]
    ports: HostFinalizationPorts


@dataclass(frozen=True)
class TurnSnapshot:
    handle: TurnHandle
    phase: TurnPhase
    result: dict[str, Any]


class SubmissionGateway(Protocol):
    """Submission persists its operation before POST; result never resubmits."""
    def chat(self, message: str, /, *, session_id: str | None = None,
             request_id: str | None = None) -> dict[str, Any]: ...


class RecoveryGateway(Protocol):
    def result(self, request_id: str) -> dict[str, Any]: ...


class TurnStateMachine:
    """One transition policy shared with ProfessionalTurnRuntime.

    This is a turn-local observation, not another durable acceptance authority.
    Transport ambiguity leaves the request submitted and permits only polling.
    """
    def __init__(self, handle: TurnHandle, phase: TurnPhase = TurnPhase.NEW) -> None:
        if not handle.request_id.strip():
            raise TurnProtocolViolation("request_id_missing")
        self.handle = handle
        self.phase = phase

    def transition(self, target: TurnPhase) -> None:
        if target is self.phase and target is not TurnPhase.POLLING:
            return
        ProfessionalTurnRuntime.require_transition(self.phase, target)
        self.phase = target

    def observe(self, result: dict[str, Any]) -> TurnSnapshot:
        from latka_jazn.core.chat_command_contract import (
            chatgpt_result_has_displayable_runtime_final,
            chatgpt_result_has_displayable_host_final,
        )

        observed = str(result.get("request_id") or (result.get("daemon_job") or {}).get("request_id") or "")
        if observed and observed != self.handle.request_id:
            raise TurnProtocolViolation("daemon_request_id_mismatch")
        nested = result.get("result")
        payload = nested if isinstance(nested, dict) else result
        nested_id = str(payload.get("request_id") or "")
        if nested_id and nested_id != self.handle.request_id:
            raise TurnProtocolViolation("daemon_request_id_mismatch")
        session = json_object(payload.get("session"))
        observed_session = str(session.get("session_id") or payload.get("session_id") or "")
        if self.handle.session_id and observed_session and self.handle.session_id != observed_session:
            raise TurnProtocolViolation("turn_handle_session_mismatch")
        presentation = payload.get("chatgpt_host_presentation") or {}
        if payload.get("host_finalization_pending") is True or result.get("job_status") == "awaiting_host_finalization" or presentation.get("action") == "generate_then_finalize":
            target = TurnPhase.AWAITING_HOST_FINALIZATION
        elif chatgpt_result_has_displayable_runtime_final(payload) or chatgpt_result_has_displayable_host_final(payload):
            target = TurnPhase.ACCEPTED_VISIBLE
        elif result.get("execution_failed") is True or result.get("job_status") in {"failed", "cancelled", "expired", "rejected"}:
            target = TurnPhase.FAILED
        elif result.get("execution_state") == "rejected":
            target = TurnPhase.FAILED
        elif result.get("accepted") is False:
            target = TurnPhase.FAILED
        elif self.phase is TurnPhase.AWAITING_HOST_FINALIZATION:
            target = self.phase
        else:
            target = TurnPhase.POLLING
        self.transition(target)
        return TurnSnapshot(self.handle, self.phase, result)


class RunnerOperations:
    """Shared API on ConversationRunner, with explicit worker/transport roles.

    A worker instance owns one composition and session. A transport view owns
    neither: it delegates to the existing durable gateway and daemon registry.
    """
    _gateway: SubmissionGateway | RecoveryGateway
    _machines: dict[str, TurnStateMachine]
    _snapshots: dict[str, TurnSnapshot]

    @classmethod
    def for_transport(cls, gateway: SubmissionGateway | RecoveryGateway) -> RunnerOperations:
        view = cls.__new__(cls)
        view._gateway = gateway
        view._machines = {}
        view._snapshots = {}
        return view

    def submit_turn(self, request: TurnRequest) -> TurnHandle:
        if not hasattr(self, "_gateway"):
            raise TurnProtocolViolation("submission_requires_durable_gateway")
        handle = TurnHandle(request.request_id, request.session_id)
        if handle.request_id in self._machines:
            raise TurnProtocolViolation("turn_already_submitted_use_resume")
        machine = TurnStateMachine(handle)
        self._machines[handle.request_id] = machine
        machine.transition(TurnPhase.SUBMITTED)
        # A transport exception cannot establish whether the POST was accepted.
        # Keep the identity registered locally and never replay the text.
        submit = getattr(self._gateway, "chat", None)
        if not callable(submit):
            raise TurnProtocolViolation("gateway_submission_unavailable")
        result = submit(request.text, session_id=request.session_id, request_id=request.request_id)
        if not isinstance(result, dict):
            raise TurnProtocolViolation("gateway_result_not_object")
        self._snapshots[handle.request_id] = machine.observe(json_object(result))
        return handle

    def submitted_snapshot(self, handle: TurnHandle) -> TurnSnapshot:
        snapshot = self._snapshots.get(handle.request_id)
        if snapshot is None or snapshot.handle != handle:
            raise TurnProtocolViolation("submitted_snapshot_unavailable_use_resume")
        return snapshot

    def poll_turn(self, handle: TurnHandle) -> TurnSnapshot:
        if not hasattr(self, "_gateway"):
            raise TurnProtocolViolation("poll_requires_durable_gateway")
        machine = self._machines.get(handle.request_id)
        if machine is None:
            # Restart recovery consults the authoritative existing job. No POST.
            machine = TurnStateMachine(handle, TurnPhase.SUBMITTED)
            self._machines[handle.request_id] = machine
        elif machine.handle != handle:
            raise TurnProtocolViolation("turn_handle_session_mismatch")
        poll = getattr(self._gateway, "result", None)
        if not callable(poll):
            raise TurnProtocolViolation("gateway_poll_unavailable")
        result = poll(handle.request_id)
        if not isinstance(result, dict):
            raise TurnProtocolViolation("gateway_result_not_object")
        snapshot = machine.observe(json_object(result))
        self._snapshots[handle.request_id] = snapshot
        return snapshot

    def resume_turn(self, request: ResumeRequest) -> TurnSnapshot:
        return self.poll_turn(request.handle)

    @staticmethod
    def finalize_candidate(*, config: JaznConfig, payload: dict[str, Any],
                           chat_bridge_meta: dict[str, Any], contract: dict[str, Any],
                           ports: HostFinalizationPorts) -> tuple[dict[str, Any] | None, list[str]]:
        from latka_jazn.core.finalization_service import FinalizationService

        return FinalizationService(config).finalize(
            payload=payload, chat_bridge_meta=chat_bridge_meta, contract=contract, ports=ports,
        )

    @staticmethod
    def recover_projection(*, config: JaznConfig, turn_id: str, request_id: str | None = None,
                           ports: HostFinalizationPorts | None = None) -> dict[str, Any]:
        from latka_jazn.core.finalization_service import FinalizationService

        return FinalizationService(config).recover_committed_projection(
            turn_id=turn_id, request_id=request_id, ports=ports,
        )

    @staticmethod
    def finalize_turn(request: FinalizeRequest) -> TurnSnapshot:
        from latka_jazn.core.chatgpt_host_pending_store import host_request_lifecycle_state

        reply, missing = request.ports.extract_payload(request.payload)
        if missing:
            return TurnSnapshot(request.handle, TurnPhase.FAILED, {"ok": False, "errors": missing})
        lifecycle = host_request_lifecycle_state(request.config.root, turn_id=str(reply.get("turn_id") or ""))
        binding = json_object(lifecycle.get("binding"))
        bound_request = str(binding.get("daemon_request_id") or binding.get("turn_id") or "")
        if bound_request != request.handle.request_id:
            return TurnSnapshot(request.handle, TurnPhase.FAILED, {"ok": False, "errors": ["finalization_handle_request_mismatch"]})
        bound_session = str(binding.get("session_id") or "")
        if request.handle.session_id and bound_session and request.handle.session_id != bound_session:
            return TurnSnapshot(request.handle, TurnPhase.FAILED, {"ok": False, "errors": ["finalization_handle_session_mismatch"]})
        result, errors = RunnerOperations.finalize_candidate(
            config=request.config, payload=request.payload, chat_bridge_meta=request.chat_bridge_meta,
            contract=request.contract, ports=request.ports,
        )
        # Only the durable finalization transaction may accept visibility.
        if result is None:
            return TurnSnapshot(request.handle, TurnPhase.FAILED, {"ok": False, "errors": errors})
        return TurnSnapshot(request.handle, TurnPhase.ACCEPTED_VISIBLE, result)

    def execute_turn(self, request: TurnRequest) -> TurnSnapshot:
        state = getattr(self, "state", None)
        owned_session = getattr(state, "session_id", None)
        if request.session_id and owned_session and request.session_id != owned_session:
            raise TurnProtocolViolation("turn_session_owner_mismatch")
        if "request_id" in request.options:
            raise TurnProtocolViolation("request_identity_option_override")
        handle = TurnHandle(request.request_id, request.session_id)
        machine = TurnStateMachine(handle)
        machine.transition(TurnPhase.SUBMITTED)
        result = getattr(self, "_execute_user_text")(request.text, request_id=request.request_id, **request.options)
        return machine.observe(result)

    def process_user_text(self, user_text: str, **kwargs: Any) -> dict[str, Any]:
        """Compatibility entrypoint; session execution has one implementation."""
        context = kwargs.get("_turn_context")
        request_id = kwargs.pop("request_id", None) or getattr(context, "request_id", None) or uuid.uuid4().hex
        state = getattr(self, "state", None)
        return self.execute_turn(TurnRequest(user_text, request_id, getattr(state, "session_id", None), kwargs)).result
