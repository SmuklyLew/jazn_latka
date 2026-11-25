"""Process-local model transport health, independent from daemon/host circuits."""
from __future__ import annotations

from collections import OrderedDict
from hashlib import sha256
from pathlib import Path
from threading import RLock

from latka_jazn.runtime.resilience import CircuitBreaker

# A daemon can reconstruct a speech adapter for each turn. Share its circuit
# across those instances, but never across unrelated roots, models or providers.
# No prompt, credentials, session or runtime-lifecycle state is written to disk.
_MAX_CIRCUITS = 256
_LOCK = RLock()
_CIRCUITS: OrderedDict[str, CircuitBreaker] = OrderedDict()


def model_transport_breaker(
    *, root: object | None, provider: str, endpoint: str, model: str,
) -> CircuitBreaker:
    key = sha256(repr((str(root), provider, endpoint, model)).encode("utf-8")).hexdigest()
    name = "model_transport:" + key
    if root is None:
        # Standalone/test adapters have no canonical runtime scope.
        return CircuitBreaker(name, recovery_timeout_seconds=15.0)
    # Normalize filesystem aliases without exposing the root in telemetry.
    canonical_root = str(Path(str(root)).resolve())
    key = sha256(repr((canonical_root, provider, endpoint, model)).encode("utf-8")).hexdigest()
    with _LOCK:
        existing = _CIRCUITS.get(key)
        if existing is not None:
            _CIRCUITS.move_to_end(key)
            return existing
        breaker = CircuitBreaker("model_transport:" + key, recovery_timeout_seconds=15.0)
        _CIRCUITS[key] = breaker
        if len(_CIRCUITS) > _MAX_CIRCUITS:
            _CIRCUITS.popitem(last=False)
        return breaker
