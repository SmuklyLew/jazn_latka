from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Protocol
import threading
import time

from latka_jazn.config import JaznConfig
from latka_jazn.memory.memory_sync_contracts import MemorySyncMode
from latka_jazn.memory.memory_sync_runtime import MemorySyncRuntime
from latka_jazn.memory.memory_sync_worker import MemorySyncWorkerResult
from latka_jazn.version import schema_version

SCHEMA_VERSION = schema_version("memory_sync_controller")
RuntimeBusy = Callable[[], bool]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class MemorySyncRuntimeLike(Protocol):
    runtime: Any

    def sync_once(self) -> MemorySyncWorkerResult: ...


@dataclass(slots=True)
class MemorySyncControllerStatus:
    """Non-secret state of the daemon-owned memory replication scheduler."""

    schema_version: str = SCHEMA_VERSION
    enabled: bool = False
    configured_mode: str = MemorySyncMode.OFF.value
    state: str = "not_started"
    running: bool = False
    cycle_count: int = 0
    successful_cycle_count: int = 0
    failed_cycle_count: int = 0
    skipped_busy_count: int = 0
    last_cycle_started_at_utc: str | None = None
    last_cycle_finished_at_utc: str | None = None
    last_success_at_utc: str | None = None
    last_error_at_utc: str | None = None
    last_error: str | None = None
    last_result: dict[str, Any] | None = None
    interval_seconds: float = 60.0
    busy_retry_seconds: float = 5.0
    ordinary_dialogue_allowed: bool = True
    local_memory_ready_independent_of_cloud: bool = True
    truth_boundary: str = (
        "Cloud memory synchronization is an optional daemon-owned durability task. "
        "Failures, missing credentials, writer-lease conflicts or remote outages must never block "
        "local dialogue, local memory commits, wake-state or runtime readiness."
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class MemorySyncController:
    """Bounded daemon-owned scheduler for optional encrypted memory replication.

    The controller deliberately owns *scheduling only*. Local memory commits remain
    synchronous SQLite transactions owned by ``MemoryTierStore``. Cloud work happens
    after those commits through the transactional outbox and can be paused, retried or
    disabled without changing local truth.

    The controller is fail-soft by construction:
    - mode ``off`` never starts a thread or touches the network;
    - an active user turn can pause a cycle before it starts;
    - one cycle at a time is permitted;
    - exceptions are recorded as diagnostics and never escape the background loop;
    - shutdown is bounded because the worker thread is a daemon thread.
    """

    def __init__(
        self,
        config: JaznConfig,
        *,
        runtime_busy: RuntimeBusy | None = None,
        sync_runtime: MemorySyncRuntimeLike | None = None,
        utc_now: Callable[[], str] = utc_now_iso,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.config = config
        self.runtime_busy = runtime_busy or (lambda: False)
        self.sync_runtime = sync_runtime or MemorySyncRuntime(config)
        self._utc_now = utc_now
        self._monotonic = monotonic
        raw_mode = getattr(self.sync_runtime.runtime, "mode", MemorySyncMode.OFF)
        mode = raw_mode if isinstance(raw_mode, MemorySyncMode) else MemorySyncMode(str(raw_mode))
        background = bool(getattr(config, "memory_sync_background_enabled", True))
        enabled = bool(mode is not MemorySyncMode.OFF and background)
        self.interval_seconds = max(1.0, float(getattr(config, "memory_sync_interval_seconds", 60.0)))
        self.busy_retry_seconds = max(0.25, float(getattr(config, "memory_sync_busy_retry_seconds", 5.0)))
        self.status = MemorySyncControllerStatus(
            enabled=enabled,
            configured_mode=mode.value,
            state="initialized" if enabled else ("disabled_local_only" if mode is MemorySyncMode.OFF else "disabled_background"),
            interval_seconds=self.interval_seconds,
            busy_retry_seconds=self.busy_retry_seconds,
        )
        self.shutdown_requested = threading.Event()
        self._thread: threading.Thread | None = None
        self._execution_lock = threading.Lock()
        self._next_run_monotonic = self._monotonic()

    def start(self) -> None:
        if not self.status.enabled:
            return
        if self._thread is not None and self._thread.is_alive():
            return
        self.shutdown_requested.clear()
        self.status.state = "waiting"
        self.status.running = True
        self._next_run_monotonic = self._monotonic()

        def loop() -> None:
            try:
                while not self.shutdown_requested.is_set():
                    now = self._monotonic()
                    wait_seconds = max(0.05, self._next_run_monotonic - now)
                    if self.shutdown_requested.wait(wait_seconds):
                        break
                    if self.runtime_busy():
                        self.status.state = "paused_runtime_busy"
                        self.status.skipped_busy_count += 1
                        self._next_run_monotonic = self._monotonic() + self.busy_retry_seconds
                        continue
                    self.tick(force=True)
                    self._next_run_monotonic = self._monotonic() + self.interval_seconds
            finally:
                self.status.running = False
                if self.status.state not in {"stopped", "disabled_local_only", "disabled_background"}:
                    self.status.state = "stopped"

        self._thread = threading.Thread(
            target=loop,
            name="jazn-memory-sync-controller",
            daemon=True,
        )
        self._thread.start()

    def stop(self, *, join_timeout_seconds: float = 2.0) -> None:
        self.shutdown_requested.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=max(0.0, float(join_timeout_seconds)))
        self.status.running = bool(thread is not None and thread.is_alive())
        self.status.state = "shutdown_wait_timeout" if self.status.running else "stopped"

    def tick(self, *, force: bool = False) -> MemorySyncWorkerResult | None:
        if not self.status.enabled:
            return None
        if not force and self.runtime_busy():
            self.status.state = "paused_runtime_busy"
            self.status.skipped_busy_count += 1
            return None
        if not self._execution_lock.acquire(blocking=False):
            self.status.state = "cycle_already_running"
            return None
        try:
            self.status.state = "syncing"
            self.status.last_cycle_started_at_utc = self._utc_now()
            self.status.cycle_count += 1
            try:
                result = self.sync_runtime.sync_once()
            except Exception as exc:  # background replication never kills the dialogue daemon
                self.status.failed_cycle_count += 1
                self.status.last_error_at_utc = self._utc_now()
                self.status.last_error = f"{type(exc).__name__}: {exc}"
                self.status.last_result = None
                self.status.state = "degraded"
                return None
            self.status.successful_cycle_count += 1
            self.status.last_success_at_utc = self._utc_now()
            self.status.last_error = None
            self.status.last_result = result.to_dict()
            self.status.state = "waiting"
            return result
        finally:
            self.status.last_cycle_finished_at_utc = self._utc_now()
            self._execution_lock.release()

    def status_payload(self) -> dict[str, Any]:
        return self.status.to_dict()


__all__ = ["MemorySyncController", "MemorySyncControllerStatus", "MemorySyncRuntimeLike"]
