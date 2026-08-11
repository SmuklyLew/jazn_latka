from __future__ import annotations

from datetime import datetime, timedelta, timezone

from latka_jazn.config import JaznConfig
from latka_jazn.core.rest_cycle_controller import RestCycleController
from latka_jazn.memory.dream_sandbox import DreamSandbox
from latka_jazn.memory.memory_tier_store import MemoryTierStore
from latka_jazn.memory.memory_tiers import MemoryKind, MemoryTruthStatus, ShortTermMemoryPolicy, SourceEvidence
from latka_jazn.memory.rest_wake_report import load_latest_rest_wake_report


class FakeClock:
    def __init__(self) -> None:
        self.ns = 1_000_000_000
        self.wall = datetime(2026, 8, 11, 20, 0, tzinfo=timezone.utc)

    def monotonic_ns(self) -> int:
        return self.ns

    def utc(self) -> str:
        return self.wall.isoformat()

    def advance(self, seconds: float) -> None:
        self.ns += int(seconds * 1_000_000_000)
        self.wall += timedelta(seconds=seconds)


def _seed(config: JaznConfig) -> None:
    policy = ShortTermMemoryPolicy()
    for index in range(3):
        record = policy.create(
            kind=MemoryKind.REFLECTION,
            content=f"Zweryfikowana pamięć testowa {index}: ciągłość ma być audytowalna.",
            domain=f"rest-test-{index}", mode="test", truth_status=MemoryTruthStatus.USER_CONFIRMED,
            confidence=0.9, importance=0.9 - index * 0.05,
            evidence=(SourceEvidence(source_type="test", source_id=f"src-{index}"),),
        )
        with MemoryTierStore(config.memory_tier_db_path) as store:
            store.save_record(record)


def test_controller_simulates_eight_hour_rest_without_fact_or_l3_promotion(tmp_path) -> None:
    config = JaznConfig(
        root=tmp_path,
        rest_shadow_mode=True,
        rest_idle_start_seconds=900,
        rest_cycle_interval_seconds=1800,
        rest_poll_seconds=0.1,
        rest_max_cycles_per_episode=16,
        rest_replay_limit=3,
    )
    _seed(config)
    clock = FakeClock()
    dream = DreamSandbox(config, generator=lambda prompt, items: (
        "Wewnętrzna symulacja łączy zweryfikowane źródła i pozostaje hipotezą do refleksji."
    ))
    controller = RestCycleController(
        config,
        runtime_busy=lambda: False,
        dream=dream,
        monotonic_ns=clock.monotonic_ns,
        utc_now=clock.utc,
    )
    try:
        # First cycle after 15 minutes, then 15 further cycles every 30 minutes.
        clock.advance(900)
        first = controller.tick()
        assert first and first["status"] == "completed"
        for _ in range(15):
            clock.advance(1800)
            result = controller.tick()
            assert result and result["status"] == "completed"
        clock.advance(900)  # total 8 hours since start of idle clock
        exhausted = controller.tick(force=True)
        assert exhausted and exhausted["status"] == "budget_exhausted"
        controller.stop()
        report = load_latest_rest_wake_report(config.rest_cycle_db_path)
        assert report["rest_continuity_status"] == "rest_verified"
        assert report["cycle_count"] == 16
        assert report["dream_scene_count"] == 16
        assert report["materialized_l2_candidate_count"] == 0
        assert report["verified_process_elapsed_seconds"] == 27_900.0
        assert report["verified_idle_window_seconds"] == 28_800.0
        validation = controller.store.validate()
        assert validation["factual_scene_violation_count"] == 0
        assert validation["automatic_l3_violation_count"] == 0
    finally:
        controller.close()


def test_user_activity_interrupts_slow_rest_generation_without_blocking_chat_path(tmp_path) -> None:
    import threading
    import time

    config = JaznConfig(
        root=tmp_path,
        rest_shadow_mode=True,
        rest_idle_start_seconds=1,
        rest_cycle_interval_seconds=1,
        rest_replay_limit=3,
    )
    _seed(config)
    clock = FakeClock()
    entered = threading.Event()
    release = threading.Event()

    def slow_generator(_prompt, _items):
        entered.set()
        assert release.wait(2.0)
        return "Ta symulacja zakończyła generowanie już po nadejściu aktywności użytkownika."

    controller = RestCycleController(
        config,
        runtime_busy=lambda: False,
        dream=DreamSandbox(config, generator=slow_generator),
        monotonic_ns=clock.monotonic_ns,
        utc_now=clock.utc,
    )
    clock.advance(2)
    result_box = {}
    worker = threading.Thread(target=lambda: result_box.setdefault("result", controller.tick(force=True)))
    worker.start()
    try:
        assert entered.wait(1.0)
        clock.advance(1)
        started = time.monotonic()
        controller.note_user_activity()
        assert time.monotonic() - started < 0.25
        assert controller.status.state == "user_activity_interrupt_pending"
        release.set()
        worker.join(2.0)
        assert not worker.is_alive()
        assert result_box["result"]["status"] == "skipped"
        report = load_latest_rest_wake_report(config.rest_cycle_db_path)
        assert report["rest_continuity_status"] == "rest_verified"
        assert report["dream_scene_count"] == 0
        assert report["skipped_cycle_count"] == 1
    finally:
        release.set()
        worker.join(2.0)
        controller.close()
