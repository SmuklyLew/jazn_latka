from __future__ import annotations

import inspect
from dataclasses import asdict
from typing import Any
from latka_jazn.config import JaznConfig
from latka_jazn.core.engine import JaznEngine
from latka_jazn.core.json_types import json_object
from latka_jazn.core.runtime_session_state import RuntimeSessionStateStore
from latka_jazn.core.session_provenance import build_session_provenance, repair_final_visible_integrity, validate_final_visible_integrity
from latka_jazn.core.runtime_truth_gate import apply_runtime_truth_gate
from latka_jazn.core.visible_integrity import enforce_integrity_consensus
from latka_jazn.core.turn_execution import TurnExecutionContext
from latka_jazn.core.turn_timeout import runtime_turn_timeout_seconds
from latka_jazn.memory.memory_tier_status import inspect_memory_tier_store
from latka_jazn.memory.runtime_memory import RuntimeMemoryWriteContext
from latka_jazn.memory.runtime_memory_install import install_runtime_memory
from latka_jazn.memory.wake_state_runtime import WakeStateRuntimeBridge

from latka_jazn.version import schema_version

SCHEMA_VERSION = schema_version("runtime_session")


def _update_runtime_session_state(
    state: Any,
    *,
    user_text: str,
    visible_text: str,
    intent: str,
    route: str,
) -> None:
    """Update canonical and minimal session-state implementations compatibly.

    The canonical RuntimeSessionState accepts ``visible_text`` and persists it as
    ``last_visible_text``. A few integrity tests intentionally use a minimal state
    double with the older ``update(user_text, intent, route)`` signature. Detect
    support before calling instead of converting a valid runtime turn into a
    TypeError. Minimal mutable states still receive ``last_visible_text`` when
    possible, preserving live-turn continuity without weakening canonical writes.
    """

    update = getattr(state, "update")
    kwargs: dict[str, Any] = {
        "user_text": user_text,
        "intent": intent,
        "route": route,
    }
    try:
        parameters = inspect.signature(update).parameters.values()
    except (TypeError, ValueError):
        parameters = ()
    supports_visible_text = any(
        parameter.name == "visible_text"
        or parameter.kind is inspect.Parameter.VAR_KEYWORD
        for parameter in parameters
    )
    if supports_visible_text:
        kwargs["visible_text"] = visible_text
    update(**kwargs)
    if not supports_visible_text:
        try:
            setattr(state, "last_visible_text", visible_text)
        except (AttributeError, TypeError):
            pass


class JaznRuntimeSession:
    """Wspólny rdzeń one-shot, --runtime-preview, --chat i --chat-gpt.

    Różnice między trybami dotyczą tylko cyklu życia procesu i formatu I/O; każda tura
    przechodzi przez JaznEngine.process_turn().
    """
    def __init__(
        self,
        config: JaznConfig | None = None,
        *,
        session_id: str | None = None,
        no_carryover: bool = False,
        source_client: str = "runtime_session",
    ) -> None:
        self.config = config or JaznConfig()
        self.engine = JaznEngine(self.config)
        self.transactional_memory_install_status = install_runtime_memory(self.engine)
        self.state_store = RuntimeSessionStateStore(self.config.root)
        self.state = self.state_store.load_or_create(
            session_id=session_id,
            source_client=source_client,
            no_carryover=no_carryover,
        )
        self.wake_state_bridge = WakeStateRuntimeBridge(self.config)
        self.wake_state_runtime_status = self.wake_state_bridge.hydrate_l1(session_id=self.state.session_id)
        self.restart_continuity_status = self.state_store.verify_loaded_continuity(
            self.state,
            self.wake_state_runtime_status,
        )
        self.no_carryover = no_carryover
        self._turn_count = int(self.state_store.last_load_metadata.get("continuity_turn_count") or 0)

    def _wake_state_runtime_payload(self) -> dict[str, Any]:
        status = getattr(self, "wake_state_runtime_status", None)
        to_dict = getattr(status, "to_dict", None)
        if callable(to_dict):
            payload = json_object(to_dict())
            payload["restart_continuity"] = dict(
                getattr(self, "restart_continuity_status", {}) or {}
            )
            return payload
        return {
            "schema_version": schema_version("wake_state_runtime"),
            "status": "not_initialized",
            "ok": False,
            "context": None,
            "l1_memory_id": None,
            "errors": ["wake_state_bridge_not_initialized"],
            "truth_boundary": (
                "Minimalna lub testowa sesja nie uruchomiła mostu wake_state. "
                "Brak pakietu ciągłości nie jest dowodem pustej pamięci."
            ),
        }

    def _transactional_memory_status_payload(self) -> dict[str, Any]:
        install_status = getattr(self, "transactional_memory_install_status", None)
        if install_status is None:
            return {
                "available": False,
                "reason": "installer_not_initialized",
                "install": None,
                "store": None,
                "truth_boundary": (
                    "Minimalna lub testowa sesja nie uruchomiła instalatora pamięci poprzednia linia runtime. "
                    "Brak statusu nie jest dowodem pustej ani uszkodzonej pamięci."
                ),
            }
        return {
            "available": True,
            "install": install_status.to_dict(),
            "store": inspect_memory_tier_store(
                install_status.database_path,
                full=False,
            ).to_dict(),
            "truth_boundary": (
                "Status L1/L2/L3 jest diagnostyką po zatwierdzeniu tury. "
                "Nie dowodzi poprawnego recall ani aktywnej tożsamości."
            ),
        }

    def process_user_text(
        self,
        user_text: str,
        *,
        client: str = "runtime_session",
        lifecycle: str = "runtime_session",
        session_id_source: str | None = None,
        process_reused: bool = True,
        request_id: str | None = None,
        previous_user_text: str | None = None,
        previous_visible_text: str | None = None,
        _turn_context: TurnExecutionContext | None = None,
    ) -> dict[str, Any]:
        config = getattr(self, "config", None)
        audit_db_path = getattr(config, "audit_db_path", None) if config is not None else None
        turn_context = _turn_context or TurnExecutionContext.create(
            request_id=request_id,
            session_id=self.state.session_id,
            timeout_seconds=runtime_turn_timeout_seconds(config),
            audit_db_path=audit_db_path,
        )
        persistence_available = config is not None
        memory_context_token = None
        bind_memory_context = getattr(getattr(self.engine, "runtime_memory", None), "bind_context", None)
        if callable(bind_memory_context):
            memory_context_token = bind_memory_context(
                RuntimeMemoryWriteContext(
                    session_id=self.state.session_id,
                    turn_id=turn_context.turn_id,
                    actor="user",
                    active_goal="validated_runtime_turn",
                )
            )
        if not persistence_available:
            turn_context.record_technical_event(
                "runtime_session_config_unavailable",
                {
                    "canonical_persistence_available": False,
                    "audit_persistence_available": False,
                },
            )
        live_previous_user = str(previous_user_text or "").strip() or None
        current_previous_user = live_previous_user or (str(self.state.last_user_text or "").strip() or None)
        current_previous_visible = str(previous_visible_text or getattr(self.state, "last_visible_text", None) or "").strip() or None
        turn_scoped_no_carryover = bool(self.no_carryover and not current_previous_user)
        ctx = {
            "client": client,
            "lifecycle": lifecycle,
            "session_id": self.state.session_id,
            "no_carryover": turn_scoped_no_carryover,
            "request_id": turn_context.request_id,
            "_turn_context": turn_context,
            "wake_state_runtime": self._wake_state_runtime_payload(),
        }
        if current_previous_user:
            ctx["previous_user_text"] = current_previous_user
            if not live_previous_user:
                ctx["previous_detected_intent"] = self.state.last_intent
                ctx["previous_runtime_route"] = self.state.last_route
        if current_previous_visible:
            ctx["previous_visible_text"] = current_previous_visible
        try:
            envelope = self.engine.process_turn(user_text, client_context=ctx)
            with turn_context.stage("final_result_serialization"):
                env = envelope.to_dict()
                decision = (env.get("cognitive_frame") or {}).get("conversation_decision") or {}
                runtime_provenance = decision.get("runtime_provenance") or {}
                result = {
                    "schema_version": SCHEMA_VERSION,
                    "session": self.state.to_dict(),
                    "session_id_source": session_id_source or "generated",
                    "trace": env.get("trace"),
                    "conversation_decision": decision,
                    "runtime_turn_contract": env.get("runtime_turn_contract"),
                    "final_response_contract": env.get("final_response_contract"),
                    "final_visible_text": env.get("final_visible_text"),
                    "runtime_provenance": runtime_provenance,
                    "exact_runtime_text": runtime_provenance.get("exact_runtime_text"),
                }

            with turn_context.stage("integrity_validation"):
                engine_contract_integrity = dict(
                    ((result.get("final_response_contract") or {}).get("final_visible_integrity") or {})
                )
                if isinstance(engine_contract_integrity.get("valid"), bool):
                    result["final_visible_integrity_pre_repair_contract_valid"] = engine_contract_integrity["valid"]
                result, integrity_repair_audit = repair_final_visible_integrity(result)
                result["final_visible_integrity"] = validate_final_visible_integrity(result)
                if integrity_repair_audit:
                    result["final_visible_integrity"]["repair_audit"] = integrity_repair_audit
                    result["final_visible_integrity_repair_audit"] = integrity_repair_audit
                contract = dict(result.get("final_response_contract") or {})
                contract["final_visible_integrity"] = dict(result["final_visible_integrity"])
                result["final_response_contract"] = contract
                decision = dict(result.get("conversation_decision") or {})
                decision["origin_truth_valid"] = bool(result["final_visible_integrity"].get("origin_truth_valid"))
                decision["origin_truth_errors"] = list(result["final_visible_integrity"].get("errors") or [])
                result["conversation_decision"] = decision

            with turn_context.stage("runtime_truth_gate"):
                result, gate_payload = apply_runtime_truth_gate(result)
            with turn_context.stage("consensus"):
                result, consensus = enforce_integrity_consensus(result)
                result["final_visible_integrity_consensus"] = consensus

            gate_payload = dict(result.get("runtime_truth_gate") or gate_payload)
            if gate_payload.get("normal_response_allowed") is False:
                result["final_visible_integrity"]["runtime_truth_gate_blocked"] = not bool(gate_payload.get("ok"))
                result["final_visible_integrity"]["truthful_degraded_disclosure"] = bool(gate_payload.get("truthful_degraded_disclosure"))
                result["final_visible_integrity"]["runtime_truth_gate_errors"] = list(gate_payload.get("errors") or [])

            integrity = result.get("final_visible_integrity") or {}
            answer_ok = bool(
                str(result.get("final_visible_text") or "").strip()
                and integrity.get("valid") is True
                and integrity.get("consensus") is True
                and consensus.get("mismatch") is False
                and gate_payload.get("ok") is True
                and gate_payload.get("normal_response_allowed") is not False
                and result.get("normal_response_blocked") is not True
                and turn_context.can_continue()
            )
            result["answer_ok"] = answer_ok
            result["ok"] = answer_ok
            if persistence_available:
                commit_status = turn_context.commit_if_allowed(result, job_status="completed")
            else:
                commit_status = turn_context.reject_staging(reason="runtime_config_unavailable")
                commit_status["available"] = False
                commit_status["diagnostic"] = "canonical persistence skipped because session config is unavailable"
                commit_status["persistence_degraded"] = bool(answer_ok)
            canonical_persistence_ok = bool(commit_status.get("committed"))
            persistence_degraded = bool(answer_ok and not canonical_persistence_ok)
            result["canonical_persistence"] = commit_status
            result["canonical_persistence_ok"] = canonical_persistence_ok
            result["persistence_degraded"] = persistence_degraded
            result["persistence_state"] = (
                "committed" if canonical_persistence_ok
                else "degraded" if persistence_degraded
                else "not_committed"
            )

            result["transactional_memory"] = self._transactional_memory_status_payload()
            result["wake_state_runtime"] = self._wake_state_runtime_payload()

            if answer_ok:
                _update_runtime_session_state(
                    self.state,
                    user_text=user_text,
                    visible_text=str(result.get("final_visible_text") or ""),
                    intent=str(decision.get("detected_user_intent") or "unknown"),
                    route=str(decision.get("route") or "unknown"),
                )
                self._turn_count += 1
                try:
                    save_status = self.state_store.save(
                        self.state,
                        continuity_context=self.wake_state_runtime_status,
                        turn_count=self._turn_count,
                    )
                except Exception as exc:
                    save_status = {
                        "saved": False,
                        "reason": "session_checkpoint_failed",
                        "error_code": type(exc).__name__,
                        "error": str(exc),
                        "persistence_degraded": True,
                    }
                    result["persistence_degraded"] = True
                    result["persistence_state"] = "degraded"
            else:
                save_status = {
                    "saved": False,
                    "reason": commit_status.get("reason") or "turn_not_committed",
                    "persistence_degraded": False,
                }
            result["session_persistence"] = dict(save_status)
            result["session_persistence_ok"] = bool(save_status.get("saved"))
            result["session"] = self.state.to_dict()
            with turn_context.stage("provenance"):
                session_provenance = build_session_provenance(
                    session_id=self.state.session_id,
                    client=client,
                    lifecycle=lifecycle,
                    process_reused=process_reused,
                    engine_reused_between_turns=True,
                    load_metadata=self.state_store.last_load_metadata,
                    save_status=save_status,
                )
                session_provenance["final_visible_integrity_valid"] = bool(integrity.get("valid"))
                session_provenance["transactional_memory_ready"] = bool(
                    ((result.get("transactional_memory") or {}).get("store") or {}).get("ready")
                )
                result["session_provenance"] = session_provenance

            final_status = (
                "completed_persistence_degraded"
                if result.get("ok") and result.get("persistence_degraded")
                else "completed" if result.get("ok")
                else "rejected"
            )
            turn_context.finalize_total(status=final_status)
            audit_status = turn_context.persist_audit()
            result["turn_audit_persistence"] = audit_status
            result["audit_persistence_ok"] = bool(audit_status.get("ok"))
            result["audit_persistence_degraded"] = not bool(audit_status.get("ok"))
            result["turn_telemetry"] = turn_context.snapshot()
            return result
        except BaseException as exc:
            turn_context.reject_staging(reason=type(exc).__name__)
            turn_context.record_technical_event(
                "runtime_turn_failed",
                {"error_code": type(exc).__name__, "error": str(exc)},
            )
            turn_context.finalize_total(status="failed", error_code=type(exc).__name__)
            turn_context.persist_audit(event_type="runtime_turn_failed")
            raise
        finally:
            if memory_context_token is not None:
                reset_memory_context = getattr(getattr(self.engine, "runtime_memory", None), "reset_context", None)
                if callable(reset_memory_context):
                    reset_memory_context(memory_context_token)

    def close(self) -> None:
        bridge = getattr(self, "wake_state_bridge", None)
        try:
            try:
                self.state_store.save(
                    self.state,
                    continuity_context=getattr(self, "wake_state_runtime_status", None),
                    turn_count=getattr(self, "_turn_count", 0),
                )
            except Exception:
                pass
            try:
                if bridge is not None:
                    bridge.end_session(self.state.session_id)
            except Exception:
                pass
        finally:
            self.engine.shutdown()
