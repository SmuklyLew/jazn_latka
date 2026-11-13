"""Bounded TPA event draining with a continuously producing synthetic source.

No Ollama, daemon, production MEMORY or unbounded background test threads.
"""
from __future__ import annotations

import queue
import threading
import time
from types import SimpleNamespace
from typing import cast

import pytest

pytest.importorskip("PySide6")

from tools.jazn_run_studio.core import Controller
from tools.jazn_run_studio.tpa_live import (
    TPA_EVENTS_PER_CHANNEL, capture_action, drain,
)
from tools.jazn_run_studio.tpa_execution_plan import PhaseDeadline


class FloodQueue:
    """An always-busy producer, capped so a broken drain still ends the test."""
    def __init__(self, source: str, count: int = 20_000) -> None:
        self.source = source
        self.count = count
        self.position = 0

    def get_nowait(self):
        if self.position >= self.count:
            raise queue.Empty
        number = self.position
        self.position += 1
        return (self.source, "state", {"number": number})


def _core() -> SimpleNamespace:
    return SimpleNamespace(
        critical_events=FloodQueue("critical"),
        events=FloodQueue("ordinary"),
    )


def test_continuous_producers_do_not_starve_each_other_or_consumer() -> None:
    core = _core()
    start = time.monotonic()
    batch = drain(cast(Controller, core))
    elapsed = time.monotonic() - start
    assert len(batch) == 2 * TPA_EVENTS_PER_CHANNEL
    assert elapsed < 0.75
    assert [event[2]["number"] for event in batch if event[0] == "critical"] == list(range(TPA_EVENTS_PER_CHANNEL))
    assert [event[2]["number"] for event in batch if event[0] == "ordinary"] == list(range(TPA_EVENTS_PER_CHANNEL))
    assert core.critical_events.position == TPA_EVENTS_PER_CHANNEL
    assert core.events.position == TPA_EVENTS_PER_CHANNEL


class PendingAction:
    key = "status"
    state = "running"
    done = threading.Event()
    returncode = None
    error = None


def test_live_action_checks_cancel_between_bounded_event_batches() -> None:
    core = _core()
    job = PendingAction()
    core.start_action = lambda _key: job
    core.redactor = SimpleNamespace(text=str)
    ticks = 0

    def cancel() -> None:
        nonlocal ticks
        ticks += 1
        if ticks >= 3:
            raise InterruptedError("operator_cancelled")

    started = time.monotonic()
    with pytest.raises(InterruptedError, match="operator_cancelled"):
        capture_action(cast(Controller, core), "status", cancel, [])
    assert time.monotonic() - started < 1.0
    assert ticks == 3
    assert core.critical_events.position <= 3 * TPA_EVENTS_PER_CHANNEL
    assert core.events.position <= 3 * TPA_EVENTS_PER_CHANNEL


def test_live_action_checks_generation_deadline_despite_event_flood() -> None:
    core = _core()
    job = PendingAction()
    core.start_action = lambda _key: job
    core.redactor = SimpleNamespace(text=str)
    deadline = PhaseDeadline({"generation": 0.16})
    deadline.enter("generation")
    counts = 0

    def check() -> None:
        nonlocal counts
        counts += 1
        deadline.check()

    with pytest.raises(TimeoutError, match="generation"):
        capture_action(cast(Controller, core), "status", check, [])
    assert counts >= 1
    assert core.critical_events.position < 20_000
    assert core.events.position < 20_000


def test_real_concurrent_producer_cannot_delay_tpa_deadline() -> None:
    """A producer adds events while consumer batches and clock keep advancing."""
    critical: queue.SimpleQueue = queue.SimpleQueue()
    ordinary: queue.Queue = queue.Queue()
    core = SimpleNamespace(critical_events=critical, events=ordinary)
    stop = threading.Event()
    ready = threading.Event()

    def produce() -> None:
        sequence = 0
        while not stop.is_set() and sequence < 10_000:
            critical.put(("critical", "state", {"number": sequence}))
            ordinary.put(("ordinary", "state", {"number": sequence}))
            sequence += 1
            ready.set()
            # Yield long enough to ensure production overlaps consumption.
            if sequence % 10 == 0:
                time.sleep(0.001)

    producer = threading.Thread(target=produce, daemon=True)
    producer.start()
    try:
        assert ready.wait(2)
        deadline = PhaseDeadline({"generation": 0.055})
        deadline.enter("generation")
        seen: dict[str, list[int]] = {"critical": [], "ordinary": []}
        with pytest.raises(TimeoutError, match="generation"):
            while True:
                batch = drain(cast(Controller, core))
                assert len(batch) <= 2 * TPA_EVENTS_PER_CHANNEL
                for source, _kind, value in batch:
                    seen[source].append(value["number"])
                deadline.check()
                time.sleep(0.004)
        assert all(items == sorted(items) for items in seen.values())
        assert producer.is_alive()  # The deadline fired before production completed.
    finally:
        stop.set()
        producer.join(timeout=2.0)
    assert not producer.is_alive()
