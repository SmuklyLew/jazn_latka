from __future__ import annotations

"""Canonical conversation-runtime convergence layer.

This module adds explicit turn-state lineage and a normalized linguistic frame
without introducing another launcher, parser, memory owner, model identity, or
finalization owner. ``main.py`` remains the composition/control plane and model
providers remain language executors.
"""

from dataclasses import asdict, dataclass, field
from enum import StrEnum
import hashlib
import json
import os
from pathlib import Path
import threading
from typing import Any, Mapping

from latka_jazn.core.runtime_session import JaznRuntimeSession as _BaseRuntimeSession
from latka_jazn.version import schema_version

SCHEMA_VERSION = schema_version("conversation_runtime_convergence")
TURN_STATE_SCHEMA_VERSION = schema_version("conversation_turn_state")
LINGUISTIC_FRAME_SCHEMA_VERSION = schema_version("conversation_linguistic_frame")
LEDGER_SCHEMA_VERSION = schema_version("conversation_turn_ledger")


class ConversationTurnState(StrEnum):
    RECEIVED = "received"
    ADMITTED = "admitted"
    CONTEXT_READY = "context_ready"
    MODEL_PENDING = "model_pending"
    MODEL_RESULT_READY = "model_result_ready"
    TOOL_PENDING = "tool_pending"
    TOOL_RESULT_READY = "tool_result_ready"
    HOST_GENERATION_PENDING = "host_generation_pending"
    HOST_CANDIDATE_READY = "host_candidate_ready"
    FINALIZATION_PENDING = "finalization_pending"
    FINALIZED = "finalized"
    VISIBLE_COMMITTED = "visible_committed"
    REJECTED = "rejected"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"
    INDETERMINATE = "indeterminate"
    HOST_FINALIZATION_EXPIRED = "host_finalization_expired"
    PROVIDER_UNAVAILABLE = "provider_unavailable"


_ALLOWED_TRANSITIONS: dict[ConversationTurnState, frozenset[ConversationTurnState]] = {
    ConversationTurnState.RECEIVED: frozenset({ConversationTurnState.ADMITTED, ConversationTurnState.REJECTED}),
    ConversationTurnState.ADMITTED: frozenset({ConversationTurnState.CONTEXT_READY, ConversationTurnState.REJECTED}),
    ConversationTurnState.CONTEXT_READY: frozenset(
        {
            ConversationTurnState.MODEL_PENDING,
            ConversationTurnState.HOST_GENERATION_PENDING,
            ConversationTurnState.FINALIZATION_PENDING,
            ConversationTurnState.REJECTED,
        }
    ),
    ConversationTurnState.MODEL_PENDING: frozenset(
        {
            ConversationTurnState.MODEL_RESULT_READY,
            ConversationTurnState.TIMED_OUT,
            ConversationTurnState.CANCELLED,
            ConversationTurnState.PROVIDER_UNAVAILABLE,
        }
    ),
    ConversationTurnState.MODEL_RESULT_READY: frozenset(
        {
            ConversationTurnState.TOOL_PENDING,
            ConversationTurnState.HOST_GENERATION_PENDING,
            ConversationTurnState.FINALIZATION_PENDING,
            ConversationTurnState.REJECTED,
        }
    ),
    ConversationTurnState.TOOL_PENDING: frozenset(
        {
            ConversationTurnState.TOOL_RESULT_READY,
            ConversationTurnState.TIMED_OUT,
            ConversationTurnState.CANCELLED,
            ConversationTurnState.REJECTED,
        }
    ),
    ConversationTurnState.TOOL_RESULT_READY: frozenset(
        {ConversationTurnState.MODEL_PENDING, ConversationTurnState.FINALIZATION_PENDING}
    ),
    ConversationTurnState.HOST_GENERATION_PENDING: frozenset(
        {
            ConversationTurnState.HOST_CANDIDATE_READY,
            ConversationTurnState.HOST_FINALIZATION_EXPIRED,
            ConversationTurnState.CANCELLED,
            ConversationTurnState.INDETERMINATE,
        }
    ),
    ConversationTurnState.HOST_CANDIDATE_READY: frozenset(
        {ConversationTurnState.FINALIZATION_PENDING, ConversationTurnState.REJECTED}
    ),
    ConversationTurnState.FINALIZATION_PENDING: frozenset(
        {ConversationTurnState.FINALIZED, ConversationTurnState.REJECTED, ConversationTurnState.INDETERMINATE}
    ),
    ConversationTurnState.FINALIZED: frozenset(
        {ConversationTurnState.VISIBLE_COMMITTED, ConversationTurnState.INDETERMINATE}
    ),
}


def _mapping(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return {str(key): item for key, item in value.items()}


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _sha256(value: Any) -> str:
    payload = value if isinstance(value, str) else _canonical_json(value)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def exact_input_sha256(user_text: str) -> str:
    """Hash exact user text without collapsing whitespace or case."""
    return _sha256(str(user_text))


def _state(value: ConversationTurnState | str) -> ConversationTurnState:
    if isinstance(value, ConversationTurnState):
        return value
    return ConversationTurnState(str(value))


def _event_seq(value: Any) -> int:
    """Parse a persisted event sequence without weakening static/runtime checks."""
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return int(value)
    raise TypeError(f"unsupported event sequence type: {type(value).__name__}")


@dataclass(slots=True)
class ConversationTransition:
    event_seq: int
    state_before: str | None
    state_after: str
    reason: str
    owner: str = "jazn_runtime"


@dataclass(slots=True)
class ConversationTurnStateContract:
    session_id: str
    request_id: str
    turn_id: str
    trace_id: str
    input_sha256: str
    revision: int = 1
    state: str = ConversationTurnState.RECEIVED.value
    event_seq: int = 0
    transitions: list[ConversationTransition] = field(default_factory=list)
    schema_version: str = TURN_STATE_SCHEMA_VERSION
    contract_sha256: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = asdict(self)
        unsigned = dict(payload)
        unsigned["contract_sha256"] = None
        payload["contract_sha256"] = _sha256(unsigned)
        return payload


def new_turn_state_contract(
    *, session_id: str, request_id: str, turn_id: str, trace_id: str, user_text: str
) -> ConversationTurnStateContract:
    contract = ConversationTurnStateContract(
        session_id=str(session_id or ""),
        request_id=str(request_id or ""),
        turn_id=str(turn_id or ""),
        trace_id=str(trace_id or ""),
        input_sha256=exact_input_sha256(user_text),
    )
    contract.transitions.append(
        ConversationTransition(0, None, ConversationTurnState.RECEIVED.value, "exact_user_input_received")
    )
    return contract


def advance_turn_state(
    contract: ConversationTurnStateContract,
    state_after: ConversationTurnState | str,
    *, reason: str,
) -> ConversationTurnStateContract:
    current = _state(contract.state)
    target = _state(state_after)
    if target not in _ALLOWED_TRANSITIONS.get(current, frozenset()):
        raise ValueError(f"invalid conversation turn transition: {current.value} -> {target.value}")
    contract.event_seq += 1
    contract.transitions.append(
        ConversationTransition(contract.event_seq, current.value, target.value, str(reason or "state_transition"))
    )
    contract.state = target.value
    contract.contract_sha256 = None
    return contract


def validate_turn_state_contract(
    value: Mapping[str, Any] | ConversationTurnStateContract,
) -> dict[str, Any]:
    data = value.to_dict() if isinstance(value, ConversationTurnStateContract) else _mapping(value)
    errors: list[str] = []
    for key in ("session_id", "request_id", "turn_id", "trace_id", "input_sha256", "state"):
        if not str(data.get(key) or "").strip():
            errors.append(f"missing:{key}")
    digest = str(data.get("input_sha256") or "")
    if digest and len(digest) != 64:
        errors.append("invalid:input_sha256")
    try:
        _state(str(data.get("state") or ""))
    except ValueError:
        errors.append("invalid:state")
    transitions = data.get("transitions")
    previous: ConversationTurnState | None = None
    if not isinstance(transitions, list) or not transitions:
        errors.append("missing:transitions")
    else:
        for expected_seq, item in enumerate(transitions):
            row = _mapping(item)
            try:
                seq = _event_seq(row.get("event_seq"))
            except (TypeError, ValueError):
                errors.append("invalid:event_seq")
                continue
            if seq != expected_seq:
                errors.append("invalid:event_seq_order")
            try:
                after = _state(str(row.get("state_after") or ""))
            except ValueError:
                errors.append("invalid:transition_state")
                continue
            if previous is None:
                if after is not ConversationTurnState.RECEIVED:
                    errors.append("invalid:first_state")
            elif after not in _ALLOWED_TRANSITIONS.get(previous, frozenset()):
                errors.append(f"invalid_transition:{previous.value}->{after.value}")
            previous = after
        if previous is not None and previous.value != str(data.get("state") or ""):
            errors.append("invalid:terminal_state_mismatch")
    observed = str(data.get("contract_sha256") or "")
    if observed:
        unsigned = dict(data)
        unsigned["contract_sha256"] = None
        if observed != _sha256(unsigned):
            errors.append("invalid:contract_sha256")
    return {
        "schema_version": schema_version("conversation_turn_state_validation"),
        "ok": not errors,
        "errors": errors,
        "state": data.get("state"),
        "visible_commit_ready": str(data.get("state")) == ConversationTurnState.VISIBLE_COMMITTED.value,
    }


def _advance_sequence(
    contract: ConversationTurnStateContract,
    states: list[tuple[ConversationTurnState, str]],
) -> ConversationTurnStateContract:
    for state, reason in states:
        advance_turn_state(contract, state, reason=reason)
    return contract


def build_runtime_result_turn_state(
    result: Mapping[str, Any], *, user_text: str, session_id: str, request_id: str | None
) -> dict[str, Any]:
    payload = _mapping(result)
    trace = _mapping(payload.get("trace"))
    runtime_turn = _mapping(payload.get("runtime_turn_contract"))
    final_contract = _mapping(payload.get("final_response_contract"))
    turn_id = str(trace.get("turn_id") or runtime_turn.get("turn_id") or final_contract.get("turn_id") or "")
    trace_id = str(trace.get("trace_id") or runtime_turn.get("trace_id") or final_contract.get("trace_id") or "")
    resolved_request_id = str(request_id or trace.get("request_id") or runtime_turn.get("request_id") or turn_id)
    contract = new_turn_state_contract(
        session_id=session_id,
        request_id=resolved_request_id,
        turn_id=turn_id,
        trace_id=trace_id,
        user_text=user_text,
    )
    _advance_sequence(
        contract,
        [
            (ConversationTurnState.ADMITTED, "runtime_turn_admitted"),
            (ConversationTurnState.CONTEXT_READY, "runtime_context_built"),
        ],
    )
    if payload.get("host_finalization_pending") is True:
        advance_turn_state(
            contract,
            ConversationTurnState.HOST_GENERATION_PENDING,
            reason="external_host_language_generation_required",
        )
    elif (
        payload.get("answer_ok") is True
        or (payload.get("ok") is True and payload.get("execution_state") == "final_visible_answer")
    ) and str(payload.get("final_visible_text") or "").strip():
        _advance_sequence(
            contract,
            [
                (ConversationTurnState.FINALIZATION_PENDING, "runtime_finalization_gate"),
                (ConversationTurnState.FINALIZED, "runtime_final_accepted"),
                (ConversationTurnState.VISIBLE_COMMITTED, "runtime_visible_final_committed"),
            ],
        )
    else:
        advance_turn_state(
            contract,
            ConversationTurnState.REJECTED,
            reason=str(payload.get("execution_state") or "runtime_turn_rejected"),
        )
    return contract.to_dict()


def build_host_finalized_turn_state(
    *, session_id: str, request_id: str, turn_id: str, trace_id: str, user_text_sha256: str
) -> dict[str, Any]:
    contract = ConversationTurnStateContract(
        session_id=str(session_id or ""),
        request_id=str(request_id or ""),
        turn_id=str(turn_id or ""),
        trace_id=str(trace_id or ""),
        input_sha256=str(user_text_sha256 or ""),
    )
    contract.transitions.append(
        ConversationTransition(0, None, ConversationTurnState.RECEIVED.value, "durable_request_reconstructed")
    )
    _advance_sequence(
        contract,
        [
            (ConversationTurnState.ADMITTED, "durable_request_admitted"),
            (ConversationTurnState.CONTEXT_READY, "durable_context_confirmed"),
            (ConversationTurnState.HOST_GENERATION_PENDING, "host_generation_requested"),
            (ConversationTurnState.HOST_CANDIDATE_READY, "host_candidate_received"),
            (ConversationTurnState.FINALIZATION_PENDING, "runtime_finalization_gate"),
            (ConversationTurnState.FINALIZED, "runtime_final_accepted"),
            (ConversationTurnState.VISIBLE_COMMITTED, "runtime_visible_final_committed"),
        ],
    )
    return contract.to_dict()


def build_linguistic_turn_frame(
    model_context: Mapping[str, Any], *, detected_intent: str, route: str
) -> dict[str, Any]:
    context = _mapping(model_context)
    nlg_plan = _mapping(context.get("nlg_plan"))
    thought = _mapping(context.get("operational_thought_frame"))
    full_canon = _mapping(context.get("full_canon_model_context"))
    raw_items = context.get("allowed_memory_items")
    memory_items = raw_items if isinstance(raw_items, list) else []
    task_state = _mapping(thought.get("dialogue_task_state") or context.get("dialogue_task_state"))
    item_ids: list[str] = []
    for item in memory_items:
        row = _mapping(item)
        item_id = str(row.get("item_id") or "")
        if item_id:
            item_ids.append(item_id)
    frame: dict[str, Any] = {
        "schema_version": LINGUISTIC_FRAME_SCHEMA_VERSION,
        "exact_user_text_sha256": exact_input_sha256(str(context.get("user_text") or "")),
        "detected_intent": str(detected_intent or "unknown"),
        "route": str(route or "unknown"),
        "answer_kind": str(nlg_plan.get("answer_kind") or "natural_dialogue"),
        "memory_policy": str(nlg_plan.get("memory_policy") or "none"),
        "source_policy": str(nlg_plan.get("source_policy") or "runtime_only"),
        "dialogue_task_state": task_state,
        "allowed_memory_item_ids": item_ids,
        "required_truth_boundaries": list(context.get("required_truth_boundaries") or []),
        "forbidden_claims": list(context.get("forbidden_claims") or []),
        "output_instructions": list(context.get("output_instructions") or []),
        "identity_canon_sha256": str(full_canon.get("immutable_canon_sha256") or ""),
        "runtime_owns_session_state": True,
        "runtime_owns_memory": True,
        "runtime_owns_finalization": True,
        "provider_is_language_executor_only": True,
    }
    frame["frame_sha256"] = _sha256(frame)
    return frame


def validate_linguistic_turn_frame(value: Mapping[str, Any]) -> dict[str, Any]:
    frame = _mapping(value)
    errors: list[str] = []
    for key in ("exact_user_text_sha256", "detected_intent", "route", "answer_kind", "frame_sha256"):
        if not str(frame.get(key) or "").strip():
            errors.append(f"missing:{key}")
    observed = str(frame.get("frame_sha256") or "")
    if observed:
        unsigned = dict(frame)
        unsigned.pop("frame_sha256", None)
        if observed != _sha256(unsigned):
            errors.append("invalid:frame_sha256")
    for invariant in (
        "runtime_owns_session_state",
        "runtime_owns_memory",
        "runtime_owns_finalization",
        "provider_is_language_executor_only",
    ):
        if frame.get(invariant) is not True:
            errors.append(f"invariant_false:{invariant}")
    return {
        "schema_version": schema_version("conversation_linguistic_frame_validation"),
        "ok": not errors,
        "errors": errors,
        "frame_sha256": observed or None,
    }


class ConversationTurnLedger:
    """Append-only, content-free state ledger for restart diagnostics."""

    _lock = threading.Lock()

    def __init__(self, root: Path) -> None:
        self.path = Path(root).expanduser().resolve() / "workspace_runtime" / "conversation_turn_state.jsonl"

    def append(self, contract: Mapping[str, Any]) -> dict[str, Any]:
        validation = validate_turn_state_contract(contract)
        if validation.get("ok") is not True:
            return {"ok": False, "written": False, "errors": validation.get("errors") or []}
        record: dict[str, Any] = {
            "schema_version": LEDGER_SCHEMA_VERSION,
            "session_id": contract.get("session_id"),
            "request_id": contract.get("request_id"),
            "turn_id": contract.get("turn_id"),
            "trace_id": contract.get("trace_id"),
            "input_sha256": contract.get("input_sha256"),
            "revision": contract.get("revision"),
            "event_seq": contract.get("event_seq"),
            "state": contract.get("state"),
            "contract_sha256": contract.get("contract_sha256"),
        }
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            encoded = (_canonical_json(record) + "\n").encode("utf-8")
            with self._lock:
                with self.path.open("ab") as handle:
                    handle.write(encoded)
                    handle.flush()
                    os.fsync(handle.fileno())
        except OSError as exc:
            return {"ok": False, "written": False, "error_code": type(exc).__name__, "error": str(exc)}
        return {"ok": True, "written": True, "path": str(self.path), "record_sha256": _sha256(record)}


class ConversationRunner(_BaseRuntimeSession):
    """Canonical conversation runner preserving the existing session API."""

    conversation_runtime_convergence = True

    def process_user_text(self, user_text: str, **kwargs: Any) -> dict[str, Any]:
        result = super().process_user_text(user_text, **kwargs)
        request_id_value = kwargs.get("request_id")
        request_id = str(request_id_value) if request_id_value else None
        contract = build_runtime_result_turn_state(
            result,
            user_text=user_text,
            session_id=str(getattr(self.state, "session_id", "") or ""),
            request_id=request_id,
        )
        validation = validate_turn_state_contract(contract)
        result["conversation_turn_state"] = contract
        result["conversation_turn_state_validation"] = validation
        root = getattr(getattr(self, "config", None), "root", None)
        if root is not None:
            result["conversation_turn_ledger"] = ConversationTurnLedger(Path(root)).append(contract)
        else:
            result["conversation_turn_ledger"] = {
                "ok": False,
                "written": False,
                "error_code": "runtime_root_unavailable",
            }
        if result.get("answer_ok") is True and validation.get("visible_commit_ready") is not True:
            result["answer_ok"] = False
            result["ok"] = False
            result["execution_state"] = "rejected"
            result["normal_response_blocked"] = True
            result["conversation_runtime_error"] = "visible_commit_state_not_verified"
        return result


_INSTALLED = False


def install_conversation_runner_class(*, runtime_daemon_module: Any | None = None) -> dict[str, Any]:
    """Install ConversationRunner into the existing canonical worker factories."""
    global _INSTALLED
    from latka_jazn.core import runtime_session as runtime_session_module

    current = getattr(runtime_session_module, "JaznRuntimeSession", None)
    if _INSTALLED and current is ConversationRunner:
        return {
            "schema_version": SCHEMA_VERSION,
            "installed": True,
            "already_installed": True,
            "runner": ConversationRunner.__name__,
        }

    setattr(runtime_session_module, "JaznRuntimeSession", ConversationRunner)
    if runtime_daemon_module is not None:
        setattr(runtime_daemon_module, "JaznRuntimeSession", ConversationRunner)
        server_type = getattr(runtime_daemon_module, "JaznDaemonServer", None)
        initializer = getattr(server_type, "__init__", None)
        kwdefaults = getattr(initializer, "__kwdefaults__", None)
        if isinstance(kwdefaults, dict) and "session_factory" in kwdefaults:
            kwdefaults["session_factory"] = ConversationRunner
    _INSTALLED = True
    return {
        "schema_version": SCHEMA_VERSION,
        "installed": True,
        "already_installed": False,
        "runner": ConversationRunner.__name__,
        "runtime_session_patched": True,
        "runtime_daemon_patched": runtime_daemon_module is not None,
        "spawn_pickleable": ConversationRunner.__module__ == __name__,
    }
