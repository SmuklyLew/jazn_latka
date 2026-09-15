from __future__ import annotations

"""Transport resilience primitives for Jaźń host/runtime boundaries.

The module deliberately separates retry, circuit-breaker and operation identity
concerns.  It never retries a side-effecting operation unless the caller marks
that operation as safe to repeat.  This is important for ChatGPT transport
ambiguity: a timeout after submission is not evidence that the daemon did not
receive the request.
"""

from dataclasses import asdict, dataclass
from pathlib import Path
from threading import RLock
from typing import Any, Callable, TypeVar
from collections import deque
import json
import os
import random
import time
import uuid

from latka_jazn.version import schema_version

SCHEMA_VERSION = schema_version("transport_resilience")
T = TypeVar("T")


class CircuitOpenError(RuntimeError):
    """Raised when a protected dependency is temporarily short-circuited."""


@dataclass(slots=True)
class RetryPolicy:
    max_attempts: int = 2
    base_delay_seconds: float = 0.05
    max_delay_seconds: float = 0.5
    jitter_fraction: float = 0.25

    def validate(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts_must_be_positive")
        if self.base_delay_seconds < 0 or self.max_delay_seconds < 0:
            raise ValueError("retry_delay_must_be_non_negative")
        if self.jitter_fraction < 0 or self.jitter_fraction > 1:
            raise ValueError("jitter_fraction_out_of_range")


@dataclass(slots=True)
class RetryBudgetSnapshot:
    allowed_retries: int
    window_seconds: float
    retries_in_window: int
    remaining: int
    schema_version: str = SCHEMA_VERSION


class RetryBudget:
    """Process-wide style retry budget for one dependency instance.

    Per-request retry limits alone do not prevent a retry storm when many turns
    fail at once.  This budget limits aggregate retry attempts over a rolling
    time window.
    """

    def __init__(
        self,
        *,
        allowed_retries: int = 30,
        window_seconds: float = 60.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if allowed_retries < 0:
            raise ValueError("allowed_retries_must_be_non_negative")
        if window_seconds <= 0:
            raise ValueError("window_seconds_must_be_positive")
        self.allowed_retries = int(allowed_retries)
        self.window_seconds = float(window_seconds)
        self._clock = clock
        self._events: deque[float] = deque()
        self._lock = RLock()

    def _prune(self, now: float) -> None:
        cutoff = now - self.window_seconds
        while self._events and self._events[0] <= cutoff:
            self._events.popleft()

    def consume(self) -> bool:
        now = self._clock()
        with self._lock:
            self._prune(now)
            if len(self._events) >= self.allowed_retries:
                return False
            self._events.append(now)
            return True

    def snapshot(self) -> RetryBudgetSnapshot:
        now = self._clock()
        with self._lock:
            self._prune(now)
            used = len(self._events)
            return RetryBudgetSnapshot(
                allowed_retries=self.allowed_retries,
                window_seconds=self.window_seconds,
                retries_in_window=used,
                remaining=max(0, self.allowed_retries - used),
            )


@dataclass(slots=True)
class CircuitBreakerSnapshot:
    name: str
    state: str
    consecutive_failures: int
    opened_at_epoch: float | None
    last_failure: str | None
    last_success_at_epoch: float | None
    recovery_timeout_seconds: float
    failure_threshold: int
    schema_version: str = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class CircuitBreaker:
    """Small durable CLOSED/OPEN/HALF_OPEN circuit breaker.

    Persistence is optional.  When enabled, only health metadata is stored; no
    request payload or user text is written to the breaker state file.
    """

    def __init__(
        self,
        name: str,
        *,
        failure_threshold: int = 3,
        recovery_timeout_seconds: float = 2.0,
        state_path: Path | None = None,
        wall_clock: Callable[[], float] = time.time,
    ) -> None:
        if failure_threshold < 1:
            raise ValueError("failure_threshold_must_be_positive")
        if recovery_timeout_seconds <= 0:
            raise ValueError("recovery_timeout_must_be_positive")
        self.name = str(name or "dependency")
        self.failure_threshold = int(failure_threshold)
        self.recovery_timeout_seconds = float(recovery_timeout_seconds)
        self.state_path = Path(state_path).expanduser().resolve() if state_path else None
        self._clock = wall_clock
        self._lock = RLock()
        self._state = "closed"
        self._consecutive_failures = 0
        self._opened_at_epoch: float | None = None
        self._last_failure: str | None = None
        self._last_success_at_epoch: float | None = None
        self._half_open_probe_inflight = False
        self._load()

    def _load(self) -> None:
        path = self.state_path
        if path is None or not path.is_file():
            return
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            return
        if not isinstance(payload, dict) or payload.get("name") != self.name:
            return
        state = str(payload.get("state") or "closed")
        if state not in {"closed", "open", "half_open"}:
            return
        self._state = state
        self._consecutive_failures = max(0, int(payload.get("consecutive_failures") or 0))
        raw_opened = payload.get("opened_at_epoch")
        self._opened_at_epoch = float(raw_opened) if raw_opened is not None else None
        self._last_failure = str(payload.get("last_failure") or "") or None
        raw_success = payload.get("last_success_at_epoch")
        self._last_success_at_epoch = float(raw_success) if raw_success is not None else None
        # Never inherit a half-open probe lease across process restart.
        if self._state == "half_open":
            self._half_open_probe_inflight = False

    def _persist(self) -> None:
        path = self.state_path
        if path is None:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = self.snapshot().to_dict()
        tmp = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
        try:
            with tmp.open("w", encoding="utf-8", newline="\n") as handle:
                json.dump(payload, handle, ensure_ascii=False, sort_keys=True, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, path)
        finally:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass

    def _refresh_state_for_time(self, now: float) -> None:
        if self._state != "open" or self._opened_at_epoch is None:
            return
        if now - self._opened_at_epoch >= self.recovery_timeout_seconds:
            self._state = "half_open"
            self._half_open_probe_inflight = False
            self._persist()

    def acquire(self) -> None:
        now = self._clock()
        with self._lock:
            self._refresh_state_for_time(now)
            if self._state == "open":
                raise CircuitOpenError(f"circuit_open:{self.name}")
            if self._state == "half_open":
                if self._half_open_probe_inflight:
                    raise CircuitOpenError(f"circuit_half_open_probe_inflight:{self.name}")
                self._half_open_probe_inflight = True

    def record_success(self) -> None:
        now = self._clock()
        with self._lock:
            self._state = "closed"
            self._consecutive_failures = 0
            self._opened_at_epoch = None
            self._last_failure = None
            self._last_success_at_epoch = now
            self._half_open_probe_inflight = False
            self._persist()

    def record_failure(self, reason: str) -> None:
        now = self._clock()
        with self._lock:
            self._consecutive_failures += 1
            self._last_failure = str(reason or "transport_failure")[:512]
            if self._state == "half_open" or self._consecutive_failures >= self.failure_threshold:
                self._state = "open"
                self._opened_at_epoch = now
            self._half_open_probe_inflight = False
            self._persist()

    def snapshot(self) -> CircuitBreakerSnapshot:
        now = self._clock()
        with self._lock:
            self._refresh_state_for_time(now)
            return CircuitBreakerSnapshot(
                name=self.name,
                state=self._state,
                consecutive_failures=self._consecutive_failures,
                opened_at_epoch=self._opened_at_epoch,
                last_failure=self._last_failure,
                last_success_at_epoch=self._last_success_at_epoch,
                recovery_timeout_seconds=self.recovery_timeout_seconds,
                failure_threshold=self.failure_threshold,
            )


@dataclass(slots=True)
class TransportSupervisorSnapshot:
    breaker: dict[str, Any]
    retry_budget: dict[str, Any]
    retry_policy: dict[str, Any]
    schema_version: str = SCHEMA_VERSION


class TransportSupervisor:
    """Apply bounded retry and circuit-breaker policy at one transport boundary."""

    def __init__(
        self,
        *,
        breaker: CircuitBreaker,
        retry_budget: RetryBudget | None = None,
        retry_policy: RetryPolicy | None = None,
        sleep: Callable[[float], None] = time.sleep,
        random_unit: Callable[[], float] = random.random,
        transient_error: Callable[[BaseException], bool] | None = None,
    ) -> None:
        self.breaker = breaker
        self.retry_budget = retry_budget or RetryBudget()
        self.retry_policy = retry_policy or RetryPolicy()
        self.retry_policy.validate()
        self._sleep = sleep
        self._random_unit = random_unit
        self._transient_error = transient_error or (lambda _exc: True)

    def _delay(self, retry_index: int) -> float:
        base = min(
            self.retry_policy.max_delay_seconds,
            self.retry_policy.base_delay_seconds * (2 ** max(0, retry_index - 1)),
        )
        jitter = base * self.retry_policy.jitter_fraction * self._random_unit()
        return min(self.retry_policy.max_delay_seconds, base + jitter)

    def execute(
        self,
        operation: Callable[[], T],
        *,
        retry_safe: bool,
    ) -> T:
        """Execute one protected call.

        `retry_safe=False` means one and only one transport attempt.  This is the
        required setting for side effects whose submission outcome may be
        ambiguous.  Safe read-only polls may use the bounded retry policy.
        """

        attempts = self.retry_policy.max_attempts if retry_safe else 1
        last_exc: BaseException | None = None
        for attempt in range(1, attempts + 1):
            self.breaker.acquire()
            try:
                result = operation()
            except BaseException as exc:
                last_exc = exc
                self.breaker.record_failure(f"{type(exc).__name__}:{exc}")
                transient = bool(self._transient_error(exc))
                can_retry = (
                    retry_safe
                    and transient
                    and attempt < attempts
                    and self.retry_budget.consume()
                )
                if not can_retry:
                    raise
                self._sleep(self._delay(attempt))
                continue
            else:
                self.breaker.record_success()
                return result
        if last_exc is not None:
            raise last_exc
        raise RuntimeError("transport_supervisor_unreachable_state")

    def snapshot(self) -> TransportSupervisorSnapshot:
        return TransportSupervisorSnapshot(
            breaker=self.breaker.snapshot().to_dict(),
            retry_budget=asdict(self.retry_budget.snapshot()),
            retry_policy=asdict(self.retry_policy),
        )


__all__ = [
    "CircuitBreaker",
    "CircuitBreakerSnapshot",
    "CircuitOpenError",
    "RetryBudget",
    "RetryBudgetSnapshot",
    "RetryPolicy",
    "TransportSupervisor",
    "TransportSupervisorSnapshot",
]
