from __future__ import annotations

from pathlib import Path

import pytest

from latka_jazn.runtime.resilience import (
    CircuitBreaker,
    CircuitOpenError,
    RetryBudget,
    RetryPolicy,
    TransportSupervisor,
)


def test_failed_model_transport_does_not_open_daemon_transport_circuit(
    tmp_path: Path,
) -> None:
    # Synthetic dependencies, not a live daemon or real model acceptance.
    now = [100.0]
    model_state = tmp_path / "model-breaker.json"
    model = CircuitBreaker(
        "model", failure_threshold=1, recovery_timeout_seconds=5,
        state_path=model_state, wall_clock=lambda: now[0],
    )
    daemon = CircuitBreaker(
        "daemon", failure_threshold=1, recovery_timeout_seconds=5,
        state_path=tmp_path / "daemon-breaker.json", wall_clock=lambda: now[0],
    )
    budget = RetryBudget(allowed_retries=2, window_seconds=60)
    supervisor = TransportSupervisor(
        breaker=model, retry_budget=budget,
        retry_policy=RetryPolicy(max_attempts=3),
        sleep=lambda _: None,
    )
    attempts: list[str] = []

    def timeout() -> None:
        attempts.append("model")
        raise TimeoutError("synthetic timeout")

    with pytest.raises(TimeoutError):
        supervisor.execute(timeout, retry_safe=False)
    assert attempts == ["model"]
    assert budget.snapshot().remaining == 2
    assert model.snapshot().state == "open"
    with pytest.raises(CircuitOpenError):
        supervisor.execute(timeout, retry_safe=False)
    assert attempts == ["model"]
    daemon.acquire()
    daemon.record_success()
    assert daemon.snapshot().state == "closed"

    restored = CircuitBreaker(
        "model", failure_threshold=1, recovery_timeout_seconds=5,
        state_path=model_state, wall_clock=lambda: now[0],
    )
    with pytest.raises(CircuitOpenError):
        restored.acquire()
    now[0] += 6
    restored.acquire()
    assert restored.snapshot().state == "half_open"
    with pytest.raises(CircuitOpenError):
        restored.acquire()
    restored.record_failure("synthetic recovery failed")
    assert restored.snapshot().state == "open"
    now[0] += 6
    restored.acquire()
    restored.record_success()
    assert restored.snapshot().state == "closed"
    assert daemon.snapshot().state == "closed"
