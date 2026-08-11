from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Callable
import threading
import time

from latka_jazn.config import JaznConfig
from latka_jazn.memory.continuity_readiness import build_memory_continuity_readiness
from latka_jazn.memory.dream_sandbox import DreamSandbox
from latka_jazn.memory.rest_consolidation import RestConsolidationGate
from latka_jazn.memory.rest_cycle_store import RestCycleStore
from latka_jazn.memory.rest_reflection import RestReflectionEvaluator
from latka_jazn.memory.rest_replay import RestReplayEngine
from latka_jazn.memory.rest_wake_report import RestWakeReportBuilder
from latka_jazn.version import PACKAGE_VERSION_FULL, schema_version

SCHEMA_VERSION = schema_version("rest_cycle_controller")
RuntimeBusy = Callable[[], bool]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class RestControllerStatus:
    schema_version: str = SCHEMA_VERSION
    enabled: bool = False
    shadow_mode: bool = True
    state: str = "not_started"
    episode_id: str | None = None
    cycle_count: int = 0
    last_cycle_id: str | None = None
    last_cycle_status: str | None = None
    last_cycle_at_utc: str | None = None
    last_error: str | None = None
    last_user_activity_monotonic_ns: int = 0
    local_model_required_for_dream_generation: bool = True
    external_tool_authority: bool = False
    automatic_l3_allowed: bool = False
    truth_boundary: str = (
        "Rest cycles are auditable internal computation. Scheduler activity does not prove biological sleep or consciousness; "
        "synthetic scenes have no external tool authority and cannot auto-promote to L3."
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class RestCycleController:
    """Bounded, daemon-owned idle scheduler for replay -> dream -> reflection -> consolidation."""

    def __init__(
        self,
        config: JaznConfig,
        *,
        runtime_busy: RuntimeBusy | None = None,
        store: RestCycleStore | None = None,
        replay: RestReplayEngine | None = None,
        dream: DreamSandbox | None = None,
        evaluator: RestReflectionEvaluator | None = None,
        consolidation: RestConsolidationGate | None = None,
        monotonic_ns: Callable[[], int] = time.monotonic_ns,
        utc_now: Callable[[], str] = utc_now_iso,
    ) -> None:
        self.config = config
        self.runtime_busy = runtime_busy or (lambda: False)
        self._monotonic_ns = monotonic_ns
        self._utc_now = utc_now
        self.store = store or RestCycleStore(config.rest_cycle_db_path)
        self.replay = replay or RestReplayEngine(config)
        self.dream = dream or DreamSandbox(config)
        self.evaluator = evaluator or RestReflectionEvaluator()
        self.consolidation = consolidation or RestConsolidationGate(config)
        self.wake_reports = RestWakeReportBuilder(self.store)
        self.shutdown_requested = threading.Event()
        self._thread: threading.Thread | None = None
        self._execution_lock = threading.Lock()
        self._last_user_activity_ns = self._monotonic_ns()
        self._last_cycle_ns = 0
        self.status = RestControllerStatus(
            enabled=bool(getattr(config, "rest_cycle_enabled", True)),
            shadow_mode=bool(getattr(config, "rest_shadow_mode", True)),
            state="initialized",
            last_user_activity_monotonic_ns=self._last_user_activity_ns,
        )
        try:
            recovered = self.store.recover_open_episode(
                ended_at_utc=self._utc_now(),
                ended_monotonic_ns=self._monotonic_ns(),
            )
            if recovered:
                self.wake_reports.build_and_persist(recovered)
        except Exception as exc:  # rest is non-blocking for main daemon readiness
            self.status.last_error = f"recovery:{type(exc).__name__}:{exc}"
            self.status.state = "degraded"

    def note_user_activity(self) -> None:
        now = self._monotonic_ns()
        self._last_user_activity_ns = now
        self.status.last_user_activity_monotonic_ns = now
        # Never hold up a user turn behind a possibly slow local dream-model call.
        # If a cycle is in progress, the cycle observes the newer activity timestamp
        # and closes itself without persisting a post-activity scene.
        if not self._execution_lock.acquire(blocking=False):
            self.status.state = "user_activity_interrupt_pending"
            return
        try:
            self._finish_active_episode_for_user_activity(now)
        finally:
            self._execution_lock.release()

    def _finish_active_episode_for_user_activity(self, now_ns: int) -> None:
        active = self.store.active_episode()
        if active:
            episode_id = str(active["episode_id"])
            try:
                self.store.finish_episode(
                    episode_id,
                    status="completed",
                    ended_at_utc=self._utc_now(),
                    ended_monotonic_ns=now_ns,
                )
                self.wake_reports.build_and_persist(episode_id)
            except Exception as exc:
                self.status.last_error = f"finish_on_user_activity:{type(exc).__name__}:{exc}"
            self.status.episode_id = None
        self.status.state = "active_dialogue"

    def start(self) -> None:
        if not self.status.enabled or (self._thread is not None and self._thread.is_alive()):
            return
        self.shutdown_requested.clear()
        self.status.state = "waiting_for_idle"

        def loop() -> None:
            poll = max(0.1, float(getattr(self.config, "rest_poll_seconds", 5.0)))
            while not self.shutdown_requested.wait(poll):
                try:
                    self.tick()
                except Exception as exc:  # fail-soft: background rest cannot kill daemon
                    self.status.state = "degraded"
                    self.status.last_error = f"tick:{type(exc).__name__}:{exc}"

        self._thread = threading.Thread(target=loop, name="jazn-rest-cycle-controller", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self.shutdown_requested.set()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=max(1.0, float(getattr(self.config, "rest_poll_seconds", 5.0)) + 1.0))
        active = self.store.active_episode()
        if active:
            episode_id = str(active["episode_id"])
            try:
                self.store.finish_episode(
                    episode_id,
                    status="completed",
                    ended_at_utc=self._utc_now(),
                    ended_monotonic_ns=self._monotonic_ns(),
                )
                self.wake_reports.build_and_persist(episode_id)
            except Exception as exc:
                self.status.last_error = f"stop:{type(exc).__name__}:{exc}"
        self.status.state = "stopped"

    def close(self) -> None:
        self.stop()
        self.store.close()

    def tick(self, *, force: bool = False) -> dict[str, Any] | None:
        if not self.status.enabled:
            return None
        now_ns = self._monotonic_ns()
        idle_seconds = max(0.0, (now_ns - self._last_user_activity_ns) / 1_000_000_000)
        idle_start = max(1.0, float(getattr(self.config, "rest_idle_start_seconds", 900.0)))
        interval = max(1.0, float(getattr(self.config, "rest_cycle_interval_seconds", 1800.0)))
        if not force and idle_seconds < idle_start:
            self.status.state = "waiting_for_idle"
            return None
        if self.runtime_busy():
            self.status.state = "paused_runtime_busy"
            return None
        if not force and self._last_cycle_ns and (now_ns - self._last_cycle_ns) / 1_000_000_000 < interval:
            self.status.state = "resting_between_cycles"
            return None
        if not self._execution_lock.acquire(blocking=False):
            self.status.state = "cycle_already_running"
            return None
        try:
            return self._run_cycle(idle_seconds=idle_seconds, now_ns=now_ns)
        finally:
            self._execution_lock.release()

    def _ensure_episode(self, now_ns: int) -> str:
        active = self.store.active_episode()
        if active:
            return str(active["episode_id"])
        readiness = build_memory_continuity_readiness(self.config, deep_verify=False)
        episode_id = self.store.start_episode(
            trigger="idle_threshold",
            continuity_mode=readiness.status,
            continuity_claim_allowed=readiness.continuity_claim_allowed,
            shadow_mode=self.status.shadow_mode,
            started_at_utc=self._utc_now(),
            started_monotonic_ns=now_ns,
        )
        self.status.episode_id = episode_id
        return episode_id

    def _run_cycle(self, *, idle_seconds: float, now_ns: int) -> dict[str, Any]:
        episode_id = self._ensure_episode(now_ns)
        ordinal = self.store.next_cycle_ordinal(episode_id)
        max_cycles = max(1, int(getattr(self.config, "rest_max_cycles_per_episode", 16)))
        if ordinal > max_cycles:
            self.status.state = "episode_cycle_budget_exhausted"
            return {"status": "budget_exhausted", "episode_id": episode_id, "ordinal": ordinal}
        cycle_id = self.store.begin_cycle(
            episode_id=episode_id,
            ordinal=ordinal,
            idle_seconds=idle_seconds,
            started_at_utc=self._utc_now(),
            started_monotonic_ns=now_ns,
        )
        self.status.state = "cycle_running"
        self.status.last_cycle_id = cycle_id
        phase = 0
        model_status: str | None = None
        payload: dict[str, Any] = {"cycle_id": cycle_id, "episode_id": episode_id, "ordinal": ordinal}
        try:
            recent = self.store.recent_replay_memory_ids(limit_cycles=max(1, int(getattr(self.config, "rest_replay_anti_loop_cycles", 4))))
            replay_items = self.replay.select(
                limit=max(1, int(getattr(self.config, "rest_replay_limit", 6))),
                recent_memory_ids=recent,
            )
            selected_at = self._utc_now()
            for item in replay_items:
                self.store.add_replay_item(cycle_id, item, selected_at_utc=selected_at)
            phase = 2
            self.store.update_cycle_phase(cycle_id, phase)
            payload["replay_count"] = len(replay_items)
            if self._last_user_activity_ns > now_ns:
                payload["reason"] = "user_activity_interrupted_rest_cycle"
                self.store.finish_cycle(
                    cycle_id, status="skipped", ended_at_utc=self._utc_now(),
                    ended_monotonic_ns=self._monotonic_ns(), phase_reached=phase,
                    model_status="not_started_after_user_activity", error=None, payload=payload,
                )
                self._mark_cycle(cycle_id, "skipped")
                self._finish_active_episode_for_user_activity(self._last_user_activity_ns)
                return {**payload, "status": "skipped"}
            scene, diagnostics = self.dream.generate(
                cycle_id=cycle_id,
                ordinal=ordinal,
                replay_items=replay_items,
                created_at_utc=self._utc_now(),
            )
            model_status = str(diagnostics.get("status") or "unknown")
            payload["dream_diagnostics"] = diagnostics
            if self._last_user_activity_ns > now_ns:
                payload["reason"] = "user_activity_interrupted_rest_cycle"
                self.store.finish_cycle(
                    cycle_id, status="skipped", ended_at_utc=self._utc_now(),
                    ended_monotonic_ns=self._monotonic_ns(), phase_reached=3,
                    model_status=model_status, error=None, payload=payload,
                )
                self._mark_cycle(cycle_id, "skipped")
                self._finish_active_episode_for_user_activity(self._last_user_activity_ns)
                return {**payload, "status": "skipped"}
            if scene is None:
                phase = 3
                self.store.finish_cycle(
                    cycle_id,
                    status="skipped",
                    ended_at_utc=self._utc_now(),
                    ended_monotonic_ns=self._monotonic_ns(),
                    phase_reached=phase,
                    model_status=model_status,
                    error=None,
                    payload=payload,
                )
                self._mark_cycle(cycle_id, "skipped")
                return {**payload, "status": "skipped", "reason": model_status}
            self.store.add_scene(scene, replay_items)
            phase = 3
            self.store.update_cycle_phase(cycle_id, phase, model_status=model_status)
            evaluation = self.evaluator.evaluate(scene, replay_items, created_at_utc=self._utc_now())
            self.store.add_evaluation(evaluation)
            phase = 4
            decision = self.consolidation.decide(scene, evaluation, replay_items, decided_at_utc=self._utc_now())
            self.store.add_consolidation_decision(decision)
            phase = 5
            payload.update({
                "scene_id": scene.scene_id,
                "simulation_kind": scene.simulation_kind.value,
                "evaluation_id": evaluation.evaluation_id,
                "disposition": decision.disposition.value,
                "materialized_memory_id": decision.materialized_memory_id,
                "automatic_l3_allowed": False,
            })
            self.store.finish_cycle(
                cycle_id,
                status="completed",
                ended_at_utc=self._utc_now(),
                ended_monotonic_ns=self._monotonic_ns(),
                phase_reached=phase,
                model_status=model_status,
                error=None,
                payload=payload,
            )
            self._mark_cycle(cycle_id, "completed")
            return {**payload, "status": "completed"}
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            payload["error"] = error
            try:
                self.store.finish_cycle(
                    cycle_id,
                    status="failed",
                    ended_at_utc=self._utc_now(),
                    ended_monotonic_ns=self._monotonic_ns(),
                    phase_reached=phase,
                    model_status=model_status,
                    error=error,
                    payload=payload,
                )
            finally:
                self._mark_cycle(cycle_id, "failed", error=error)
            return {**payload, "status": "failed"}

    def _mark_cycle(self, cycle_id: str, status: str, *, error: str | None = None) -> None:
        self._last_cycle_ns = self._monotonic_ns()
        self.status.cycle_count += 1
        self.status.last_cycle_id = cycle_id
        self.status.last_cycle_status = status
        self.status.last_cycle_at_utc = self._utc_now()
        self.status.last_error = error
        self.status.state = "resting_between_cycles"

    def status_payload(self, *, deep_verify: bool = False) -> dict[str, Any]:
        data = self.status.to_dict()
        data["runtime_version"] = PACKAGE_VERSION_FULL
        data["store_path"] = str(self.store.path)
        data["store_verification_mode"] = "deep" if deep_verify else "metadata"
        try:
            if deep_verify:
                data["store_validation"] = self.store.validate()
            else:
                data["store_validation"] = {"ok": True, "verification_mode": "metadata", "path": str(self.store.path)}
            data["latest_wake_report"] = RestWakeReportBuilder.bounded_context(self.wake_reports.load_latest_verified())
        except Exception as exc:
            data["store_validation"] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        return data
