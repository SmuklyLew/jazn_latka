"""Stage 05: registry pressure never replaces active or failed model circuits."""
from __future__ import annotations

from collections import OrderedDict
from pathlib import Path
from threading import Event, Thread
from typing import Any

import pytest

from latka_jazn.model_adapters import model_transport_health as health
from latka_jazn.runtime.resilience import CircuitOpenError


@pytest.mark.parametrize("state", ["closed", "open", "half_open"])
def test_registry_capacity_preserves_existing_circuit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, state: str,
) -> None:
    monkeypatch.setattr(health, "_CIRCUITS", OrderedDict())
    monkeypatch.setattr(health, "_MAX_CIRCUITS", 2)
    def get(model: str):
        return health.model_transport_breaker(root=tmp_path, provider="ollama",
                                              endpoint="http://127.0.0.1:11434", model=model)
    first = get("first")
    clock = [100.0]
    monkeypatch.setattr(first, "_clock", lambda: clock[0])
    if state != "closed":
        for _ in range(first.failure_threshold):
            first.record_failure("synthetic")
        if state == "half_open":
            clock[0] += first.recovery_timeout_seconds + 1
            first.acquire()
    second = get("second")
    denied = get("third")
    assert get("first") is first
    assert get("second") is second
    assert first.snapshot().state == state
    assert len(health._CIRCUITS) == 2
    assert denied.snapshot().last_failure == "model_transport_registry_capacity"
    assert get("fourth") is denied
    with pytest.raises(CircuitOpenError, match="model_transport_registry_capacity"):
        health.model_transport_once(denied, lambda: pytest.fail("unexpected transport"))
    if state in {"open", "half_open"}:
        with pytest.raises(CircuitOpenError):
            first.acquire()


def test_registry_pressure_during_live_operation_keeps_original_object(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(health, "_CIRCUITS", OrderedDict())
    monkeypatch.setattr(health, "_MAX_CIRCUITS", 1)
    def get(model: str):
        return health.model_transport_breaker(root=tmp_path, provider="ollama",
                                              endpoint="http://127.0.0.1:11434", model=model)
    first = get("active")
    entered, release = Event(), Event()
    results: list[Any] = []
    def operation() -> str:
        entered.set()
        if not release.wait(3):
            raise TimeoutError("synthetic wait")
        return "ok"
    worker = Thread(target=lambda: results.append(health.model_transport_once(first, operation)), daemon=True)
    worker.start()
    try:
        assert entered.wait(2)
        denied = get("other")
        with pytest.raises(CircuitOpenError):
            denied.acquire()
        assert get("active") is first
        assert len(health._CIRCUITS) == 1
    finally:
        release.set()
        worker.join(3)
    assert results == ["ok"]
    assert first.snapshot().state == "closed"
