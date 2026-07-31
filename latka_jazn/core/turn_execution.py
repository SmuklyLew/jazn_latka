from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator
import threading
import time
import uuid
import json
import os

from latka_jazn.core.json_types import json_object


TURN_STAGE_NAMES = (
    "request_accepted",
    "queue_wait",
    "worker_pickup",
    "session_initialization",
    "route_classification",
    "health_check_detection",
    "startup_status_collection",
    "timestamp_acquisition",
    "memory_use_gate",
    "memory_planning",
    "memory_reads",
    "truth_audit_generation",
    "candidate_persistence_staging",
    "synthesis",
    "finalization_timestamp_refresh",
    "host_visible_finalization",
    "integrity_validation",
    "consensus",
    "runtime_truth_gate",
    "provenance",
    "canonical_persistence_commit",
    "audit_persistence",
    "final_result_serialization",
    "total_execution_time",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class StagedSemanticWrite:
    write_id: str
    request_id: str
    turn_id: str
    session_id: str
    data_type: str
    stage: str
    created_at_utc: str
    commit: Callable[[], Any] = field(repr=False)
    compensate: Callable[[], Any] | None = field(default=None, repr=False)


class TurnExecutionContext:
    """Turn-local telemetry, cancellation and delayed semantic persistence.

    The object is shared by the timeout owner and the session worker.  Canonical
    callbacks remain in memory until the final integrity, consensus and truth
    gates authorize a commit.  A deadline/cancellation check is repeated before
    every callback so a late worker cannot write after an execution timeout.
    """

    def __init__(
        self,
        *,
        request_id: str,
        turn_id: str,
        session_id: str,
        timeout_seconds: float,
        audit_db_path: Path | None,
    ) -> None:
        self.request_id = request_id
        self.turn_id = turn_id
        self.session_id = session_id
        self.timeout_seconds = max(0.001, float(timeout_seconds))
        self.audit_db_path = Path(audit_db_path) if audit_db_path else None
        self.created_at_utc = _utc_now()
        self.created_monotonic = time.monotonic()
        self.deadline_monotonic = self.created_monotonic + self.timeout_seconds
        self._lock = threading.RLock()
        self._stages: dict[str, dict[str, Any]] = {}
        self._staged_writes: list[StagedSemanticWrite] = []
        self._technical_events: list[tuple[str, dict[str, Any]]] = []
        self._cancelled = False
        self._cancellation_reason: str | None = None
        self._cancellation_error_code: str | None = None
        self._cancelled_at_utc: str | None = None
        self._canonical_committed = False
        self._committed_write_ids: set[str] = set()
        self._rejected_write_ids: set[str] = set()
        self._audit_sequence = 0
        self.mark_stage("request_accepted", status="completed")

    @classmethod
    def create(
        cls,
        *,
        request_id: str | None = None,
        turn_id: str | None = None,
        session_id: str | None = None,
        timeout_seconds: float = 45.0,
        audit_db_path: Path | None = None,
    ) -> "TurnExecutionContext":
        return cls(
            request_id=str(request_id or uuid.uuid4()),
            turn_id=str(turn_id or uuid.uuid4()),
            session_id=str(session_id or "runtime-session"),
            timeout_seconds=timeout_seconds,
            audit_db_path=audit_db_path,
        )

    @property
    def cancelled(self) -> bool:
        with self._lock:
            return self._cancelled

    def remaining_seconds(self) -> float:
        return self.deadline_monotonic - time.monotonic()

    def _deadline_expired_locked(self) -> bool:
        return time.monotonic() >= self.deadline_monotonic

    def can_continue(self) -> bool:
        with self._lock:
            return not self._cancelled and not self._deadline_expired_locked()

    def cancel(self, *, reason: str, error_code: str = "cancelled") -> None:
        with self._lock:
            if not self._cancelled:
                self._cancelled = True
                self._cancellation_reason = reason
                self._cancellation_error_code = error_code
                self._cancelled_at_utc = _utc_now()
            for stage in self._stages.values():
                if stage.get("status") == "running":
                    self._complete_stage_locked(stage, status="cancelled", error_code=error_code)
            self._reject_staging_locked(reason=error_code)
            self.mark_stage("total_execution_time", status="cancelled", error_code=error_code)

    def start_stage(self, name: str) -> None:
        with self._lock:
            now_utc = _utc_now()
            now_mono = time.monotonic()
            self._stages[name] = {
                "started_at": now_utc,
                "completed_at": None,
                "duration_ms": None,
                "status": "running",
                "cancelled": self._cancelled,
                "cancellation_reason": self._cancellation_reason,
                "error_code": None,
                "_started_monotonic": now_mono,
            }

    def _complete_stage_locked(
        self,
        stage: dict[str, Any],
        *,
        status: str,
        error_code: str | None,
    ) -> None:
        now_mono = time.monotonic()
        started_mono = float(stage.get("_started_monotonic") or now_mono)
        stage["completed_at"] = _utc_now()
        stage["duration_ms"] = round(max(0.0, now_mono - started_mono) * 1000.0, 3)
        stage["status"] = status
        stage["cancelled"] = self._cancelled
        stage["cancellation_reason"] = self._cancellation_reason
        stage["error_code"] = error_code

    def complete_stage(self, name: str, *, status: str = "completed", error_code: str | None = None) -> None:
        with self._lock:
            stage = self._stages.get(name)
            if stage is None:
                self.start_stage(name)
                stage = self._stages[name]
            self._complete_stage_locked(stage, status=status, error_code=error_code)

    def mark_stage(self, name: str, *, status: str, error_code: str | None = None) -> None:
        with self._lock:
            self.start_stage(name)
            self.complete_stage(name, status=status, error_code=error_code)

    def mark_interval(
        self,
        name: str,
        *,
        started_monotonic: float,
        status: str = "completed",
        error_code: str | None = None,
    ) -> None:
        with self._lock:
            now_mono = time.monotonic()
            duration = max(0.0, now_mono - started_monotonic)
            self._stages[name] = {
                "started_at": None,
                "completed_at": _utc_now(),
                "duration_ms": round(duration * 1000.0, 3),
                "status": status,
                "cancelled": self._cancelled,
                "cancellation_reason": self._cancellation_reason,
                "error_code": error_code,
                "_started_monotonic": started_monotonic,
            }

    @contextmanager
    def stage(self, name: str) -> Iterator[None]:
        self.start_stage(name)
        try:
            yield
        except BaseException as exc:
            self.complete_stage(name, status="failed", error_code=type(exc).__name__)
            raise
        else:
            status = "cancelled" if self.cancelled else "completed"
            self.complete_stage(name, status=status, error_code=self._cancellation_error_code if self.cancelled else None)

    def stage_semantic_write(
        self,
        *,
        data_type: str,
        stage: str,
        commit: Callable[[], Any],
        compensate: Callable[[], Any] | None = None,
    ) -> str | None:
        with self._lock:
            if self._cancelled or self._deadline_expired_locked():
                return None
            write = StagedSemanticWrite(
                write_id=str(uuid.uuid4()),
                request_id=self.request_id,
                turn_id=self.turn_id,
                session_id=self.session_id,
                data_type=str(data_type),
                stage=str(stage),
                created_at_utc=_utc_now(),
                commit=commit,
                compensate=compensate,
            )
            self._staged_writes.append(write)
            return write.write_id

    def record_technical_event(self, event_type: str, payload: dict[str, Any]) -> None:
        with self._lock:
            self._technical_events.append((str(event_type), dict(payload or {})))

    @staticmethod
    def _gate_failure_reason(result: dict[str, Any], *, job_status: str) -> str | None:
        if job_status != "completed":
            return "job_not_completed"
        if result.get("ok") is not True:
            return "result_not_ok"
        if not str(result.get("final_visible_text") or "").strip():
            return "final_visible_text_missing"
        integrity = json_object(result.get("final_visible_integrity"))
        if integrity.get("valid") is not True:
            return "integrity_invalid"
        consensus = json_object(result.get("final_visible_integrity_consensus"))
        if consensus.get("mismatch") is True or integrity.get("consensus") is False:
            return "consensus_mismatch"
        gate = json_object(result.get("runtime_truth_gate"))
        if gate.get("ok") is not True:
            return "runtime_truth_gate_failed"
        if gate.get("normal_response_allowed") is False:
            return "normal_response_blocked"
        if result.get("normal_response_blocked") is True:
            return "normal_response_blocked"
        return None

    def _reject_staging_locked(self, *, reason: str) -> int:
        count = 0
        for write in self._staged_writes:
            if write.write_id not in self._committed_write_ids and write.write_id not in self._rejected_write_ids:
                self._rejected_write_ids.add(write.write_id)
                count += 1
        self._staged_writes.clear()
        return count

    def reject_staging(self, *, reason: str) -> dict[str, Any]:
        with self._lock:
            rejected = self._reject_staging_locked(reason=reason)
            self.mark_stage("canonical_persistence_commit", status="rejected", error_code=reason)
            return {"committed": False, "committed_count": 0, "rejected_count": rejected, "reason": reason, "persistence_degraded": False, "partial_commit_detected": False}

    def _write_recovery_outbox(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self.audit_db_path is None:
            return {"written": False, "path": None, "error_code": "recovery_outbox_path_unavailable"}
        path = self.audit_db_path.parent / "turn_persistence_recovery.jsonl"
        record = {
            "schema_version": "turn_persistence_recovery/v1",
            "created_at_utc": _utc_now(),
            "request_id": self.request_id,
            "turn_id": self.turn_id,
            "session_id": self.session_id,
            **dict(payload),
        }
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            encoded = (json.dumps(record, ensure_ascii=False, sort_keys=True, default=str) + "\n").encode("utf-8")
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            try:
                os.write(fd, encoded)
                os.fsync(fd)
            finally:
                os.close(fd)
            return {"written": True, "path": str(path), "error_code": None}
        except OSError as exc:
            return {
                "written": False,
                "path": str(path),
                "error_code": type(exc).__name__,
                "error": str(exc),
            }

    def _compensate_committed_writes(self, writes: list[StagedSemanticWrite]) -> dict[str, Any]:
        attempted = 0
        compensated: list[str] = []
        failures: list[dict[str, str]] = []
        unavailable: list[str] = []
        for write in reversed(writes):
            if write.compensate is None:
                unavailable.append(write.write_id)
                continue
            attempted += 1
            try:
                write.compensate()
                compensated.append(write.write_id)
            except Exception as exc:
                failures.append({
                    "write_id": write.write_id,
                    "error_code": type(exc).__name__,
                    "error": str(exc),
                })
        return {
            "attempted": attempted,
            "compensated_count": len(compensated),
            "compensated_write_ids": compensated,
            "unavailable_write_ids": unavailable,
            "failures": failures,
            "complete": bool(writes) and len(compensated) == len(writes) and not failures,
        }

    def commit_if_allowed(self, result: dict[str, Any], *, job_status: str) -> dict[str, Any]:
        with self._lock:
            if self._canonical_committed:
                return {
                    "committed": True, "committed_count": 0, "rejected_count": 0,
                    "reason": "already_committed", "persistence_degraded": False,
                    "partial_commit_detected": False,
                }
            if self._cancelled or self._deadline_expired_locked():
                reason = self._cancellation_error_code or "execution_timeout"
                return self.reject_staging(reason=reason)
            failure = self._gate_failure_reason(result, job_status=job_status)
            if failure:
                return self.reject_staging(reason=failure)
            writes = list(self._staged_writes)
            self.start_stage("canonical_persistence_commit")

        committed_writes: list[StagedSemanticWrite] = []
        for index, write in enumerate(writes):
            with self._lock:
                if self._cancelled or self._deadline_expired_locked():
                    reason = self._cancellation_error_code or "execution_timeout"
                    rejected = self._reject_staging_locked(reason=reason)
                    compensation = self._compensate_committed_writes(committed_writes)
                    recovery = self._write_recovery_outbox({
                        "reason": reason,
                        "partial_commit_detected": bool(committed_writes),
                        "committed_write_ids": [item.write_id for item in committed_writes],
                        "pending_write_ids": [item.write_id for item in writes[index:]],
                        "compensation": compensation,
                    })
                    self.complete_stage("canonical_persistence_commit", status="cancelled", error_code=reason)
                    return {
                        "committed": False,
                        "committed_count": len(committed_writes),
                        "rejected_count": rejected,
                        "reason": reason,
                        "persistence_degraded": True,
                        "partial_commit_detected": bool(committed_writes),
                        "compensation": compensation,
                        "recovery_outbox": recovery,
                    }
            try:
                write.commit()
            except Exception as exc:
                with self._lock:
                    rejected = self._reject_staging_locked(reason="canonical_commit_failed")
                    self.complete_stage(
                        "canonical_persistence_commit",
                        status="failed_degraded",
                        error_code=type(exc).__name__,
                    )
                compensation = self._compensate_committed_writes(committed_writes)
                recovery = self._write_recovery_outbox({
                    "reason": "canonical_commit_failed",
                    "error_code": type(exc).__name__,
                    "error": str(exc),
                    "failed_write_id": write.write_id,
                    "partial_commit_detected": bool(committed_writes),
                    "committed_write_ids": [item.write_id for item in committed_writes],
                    "pending_write_ids": [item.write_id for item in writes[index + 1:]],
                    "compensation": compensation,
                })
                return {
                    "committed": False,
                    "committed_count": len(committed_writes),
                    "rejected_count": rejected,
                    "reason": "canonical_commit_failed",
                    "error_code": type(exc).__name__,
                    "error": str(exc),
                    "failed_write_id": write.write_id,
                    "persistence_degraded": True,
                    "partial_commit_detected": bool(committed_writes),
                    "compensation": compensation,
                    "recovery_outbox": recovery,
                }
            with self._lock:
                self._committed_write_ids.add(write.write_id)
            committed_writes.append(write)

        with self._lock:
            self._staged_writes.clear()
            self._canonical_committed = True
            self.complete_stage("canonical_persistence_commit", status="completed")
        return {
            "committed": True,
            "committed_count": len(committed_writes),
            "rejected_count": 0,
            "reason": "success_gates_passed",
            "persistence_degraded": False,
            "partial_commit_detected": False,
            "compensation": {
                "attempted": 0, "compensated_count": 0, "compensated_write_ids": [],
                "unavailable_write_ids": [], "failures": [], "complete": False,
            },
            "recovery_outbox": {"written": False, "path": None, "error_code": None},
        }

    def finalize_total(self, *, status: str, error_code: str | None = None) -> None:
        with self._lock:
            now_mono = time.monotonic()
            self._stages["total_execution_time"] = {
                "started_at": self.created_at_utc,
                "completed_at": _utc_now(),
                "duration_ms": round(max(0.0, now_mono - self.created_monotonic) * 1000.0, 3),
                "status": status,
                "cancelled": self._cancelled,
                "cancellation_reason": self._cancellation_reason,
                "error_code": error_code,
                "_started_monotonic": self.created_monotonic,
            }

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            stages: dict[str, dict[str, Any]] = {}
            for name in TURN_STAGE_NAMES:
                raw = dict(self._stages.get(name) or {})
                raw.pop("_started_monotonic", None)
                stages[name] = raw or {
                    "started_at": None,
                    "completed_at": None,
                    "duration_ms": None,
                    "status": "not_started",
                    "cancelled": self._cancelled,
                    "cancellation_reason": self._cancellation_reason,
                    "error_code": None,
                }
            return {
                "schema_version": "turn_execution_context/v1",
                "request_id": self.request_id,
                "turn_id": self.turn_id,
                "session_id": self.session_id,
                "created_at_utc": self.created_at_utc,
                "timeout_seconds": self.timeout_seconds,
                "deadline_remaining_seconds": round(self.remaining_seconds(), 6),
                "cancellation": {
                    "cancelled": self._cancelled,
                    "reason": self._cancellation_reason,
                    "error_code": self._cancellation_error_code,
                    "cancelled_at_utc": self._cancelled_at_utc,
                },
                "canonical_persistence": {
                    "staged_current": len(self._staged_writes),
                    "committed_total": len(self._committed_write_ids),
                    "rejected_total": len(self._rejected_write_ids),
                    "commit_complete": self._canonical_committed,
                },
                "stages": stages,
            }

    def persist_audit(self, *, event_type: str = "runtime_turn_telemetry") -> dict[str, Any]:
        """Persist non-canonical telemetry without changing the turn outcome.

        Audit storage is deliberately fail-soft.  A locked, missing or damaged
        runtime_audit database must not mask an execution timeout and must not
        turn an already validated response into a failed turn after canonical
        persistence has completed.
        """

        if self.audit_db_path is None:
            return {
                "ok": False,
                "available": False,
                "event_type": event_type,
                "technical_event_count": 0,
                "error_code": "audit_db_unavailable",
                "error": None,
            }

        from latka_jazn.audit.audit_context_store import AuditContextStore

        with self._lock:
            technical = list(self._technical_events)
            self._audit_sequence += 1
            sequence = self._audit_sequence
        self.start_stage("audit_persistence")
        store: AuditContextStore | None = None
        try:
            store = AuditContextStore(self.audit_db_path)
            for technical_type, payload in technical:
                enriched = {
                    "request_id": self.request_id,
                    "turn_id": self.turn_id,
                    "session_id": self.session_id,
                    **payload,
                }
                store.append_event(
                    technical_type,
                    enriched,
                    source="TurnExecutionContext",
                    actor="runtime",
                    tags=["technical_audit", "non_canonical"],
                    trace_id=self.request_id,
                    turn_id=self.turn_id,
                )
            self.complete_stage("audit_persistence", status="completed")
            store.append_event(
                event_type,
                {"audit_sequence": sequence, **self.snapshot()},
                source="TurnExecutionContext",
                actor="runtime",
                tags=["turn_telemetry", "non_canonical"],
                trace_id=self.request_id,
                turn_id=self.turn_id,
            )
            with self._lock:
                for _ in range(min(len(technical), len(self._technical_events))):
                    self._technical_events.pop(0)
            return {
                "ok": True,
                "available": True,
                "event_type": event_type,
                "technical_event_count": len(technical),
                "error_code": None,
                "error": None,
            }
        except Exception as exc:
            self.complete_stage(
                "audit_persistence",
                status="failed_non_blocking",
                error_code=type(exc).__name__,
            )
            return {
                "ok": False,
                "available": True,
                "event_type": event_type,
                "technical_event_count": len(technical),
                "error_code": type(exc).__name__,
                "error": str(exc),
            }
        finally:
            if store is not None:
                try:
                    store.close()
                except Exception:
                    pass
