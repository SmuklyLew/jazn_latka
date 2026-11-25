"""Process-local model transport health, independent from daemon/host circuits."""
from __future__ import annotations

from collections import OrderedDict
from hashlib import sha256
from os.path import normcase
from pathlib import Path
from threading import RLock
from typing import Callable, TypeVar
from urllib.error import HTTPError

from latka_jazn.runtime.resilience import CircuitBreaker, CircuitBreakerSnapshot, CircuitOpenError

# A daemon can reconstruct a speech adapter for each turn. Share its circuit
# across those instances, but never across unrelated roots, models or providers.
# No prompt, credentials, session or runtime-lifecycle state is written to disk.
_MAX_CIRCUITS = 256
_LOCK = RLock()
_CIRCUITS: OrderedDict[str, CircuitBreaker] = OrderedDict()


class _CapacityDeniedCircuit(CircuitBreaker):
    """Bounded admission refusal, not a replacement for any existing circuit.

    The shared refusal never admits a model call or accumulates per-key state.
    Existing routes continue to use their original circuit until process exit.
    """

    def acquire(self) -> None:
        raise CircuitOpenError("model_transport_registry_capacity")

    def snapshot(self) -> CircuitBreakerSnapshot:
        return CircuitBreakerSnapshot(
            name=self.name, state="open", consecutive_failures=0,
            opened_at_epoch=None, last_failure="model_transport_registry_capacity",
            last_success_at_epoch=None, recovery_timeout_seconds=self.recovery_timeout_seconds,
            failure_threshold=self.failure_threshold,
        )

    def record_success(self) -> None:
        pass

    def record_failure(self, reason: str) -> None:
        pass

    def record_non_transient_response(self) -> None:
        pass


_CAPACITY_DENIED = _CapacityDeniedCircuit("model_transport_registry_capacity")


def model_transport_breaker(
    *, root: object | None, provider: str, endpoint: str, model: str,
) -> CircuitBreaker:
    key = sha256(repr((str(root), provider, endpoint, model)).encode("utf-8")).hexdigest()
    name = "model_transport:" + key
    if root is None:
        # Standalone/test adapters have no canonical runtime scope.
        return CircuitBreaker(name, recovery_timeout_seconds=15.0)
    # Normalize filesystem aliases without exposing the root in telemetry.
    canonical_root = normcase(str(Path(str(root)).resolve()))
    key = sha256(repr((canonical_root, provider, endpoint, model)).encode("utf-8")).hexdigest()
    with _LOCK:
        existing = _CIRCUITS.get(key)
        if existing is not None:
            _CIRCUITS.move_to_end(key)
            return existing
        # Eviction could split one active dependency across two independent
        # health objects (or reset OPEN/HALF_OPEN). Fail closed at capacity,
        # without evicting existing keys or allocating another registry entry.
        if len(_CIRCUITS) >= _MAX_CIRCUITS:
            return _CAPACITY_DENIED
        breaker = CircuitBreaker("model_transport:" + key, recovery_timeout_seconds=15.0)
        _CIRCUITS[key] = breaker
        return breaker

_T = TypeVar("_T")


def record_model_transport_error(breaker: CircuitBreaker, exc: Exception) -> None:
    """Classify transport failures without retaining exception text or credentials."""
    if isinstance(exc, HTTPError):
        if exc.code not in {408, 429} and not 500 <= exc.code <= 599:
            breaker.record_non_transient_response()
            return
        breaker.record_failure(f"http_error_{exc.code}")
        return
    breaker.record_failure(type(exc).__name__)


def model_transport_once(breaker: CircuitBreaker, operation: Callable[[], _T]) -> _T:
    """Exactly one attempt; an uncertain POST is never retried here."""
    breaker.acquire()
    try:
        value = operation()
    except Exception as exc:
        record_model_transport_error(breaker, exc)
        raise
    breaker.record_success()
    return value
