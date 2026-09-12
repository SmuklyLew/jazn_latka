from __future__ import annotations

from dataclasses import dataclass
import threading
import time

from latka_jazn.config import JaznConfig
from latka_jazn.memory.memory_sync_contracts import MemorySyncMode
from latka_jazn.memory.memory_sync_controller import MemorySyncController
from latka_jazn.memory.memory_sync_worker import MemorySyncWorkerResult


@dataclass
class _RuntimeConfig:
    mode: MemorySyncMode


class _FakeSyncRuntime:
    def __init__(self, mode: MemorySyncMode, *, fail: bool = False) -> None:
        self.runtime = _RuntimeConfig(mode)
        self.fail = fail
        self.calls = 0
        self.called = threading.Event()

    def sync_once(self) -> MemorySyncWorkerResult:
        self.calls += 1
        self.called.set()
        if self.fail:
            raise RuntimeError("remote unavailable")
        return MemorySyncWorkerResult(push_claimed=2, push_accepted=2, cursor_before=1, cursor_after=3)


def _cfg(tmp_path, *, mode: str, background: bool = True) -> JaznConfig:
    cfg = JaznConfig(root=tmp_path)
    cfg.memory_sync_mode = mode
    cfg.memory_sync_background_enabled = background
    cfg.memory_sync_interval_seconds = 0.05
    cfg.memory_sync_busy_retry_seconds = 0.02
    return cfg


def test_local_only_mode_never_starts_background_thread_or_sync(tmp_path) -> None:
    fake = _FakeSyncRuntime(MemorySyncMode.OFF)
    controller = MemorySyncController(_cfg(tmp_path, mode="off"), sync_runtime=fake)
    controller.start()
    time.sleep(0.03)
    status = controller.status_payload()
    assert status["enabled"] is False
    assert status["running"] is False
    assert status["state"] == "disabled_local_only"
    assert fake.calls == 0


def test_manual_tick_records_full_result_without_blocking_local_truth(tmp_path) -> None:
    fake = _FakeSyncRuntime(MemorySyncMode.BACKUP)
    controller = MemorySyncController(_cfg(tmp_path, mode="backup"), sync_runtime=fake)
    result = controller.tick(force=True)
    assert result is not None
    assert result.push_accepted == 2
    status = controller.status_payload()
    assert status["cycle_count"] == 1
    assert status["successful_cycle_count"] == 1
    assert status["failed_cycle_count"] == 0
    assert status["last_result"]["cursor_after"] == 3
    assert status["ordinary_dialogue_allowed"] is True
    assert status["local_memory_ready_independent_of_cloud"] is True


def test_failure_is_fail_soft_and_preserved_as_diagnostic(tmp_path) -> None:
    fake = _FakeSyncRuntime(MemorySyncMode.BACKUP, fail=True)
    controller = MemorySyncController(_cfg(tmp_path, mode="backup"), sync_runtime=fake)
    assert controller.tick(force=True) is None
    status = controller.status_payload()
    assert status["state"] == "degraded"
    assert status["failed_cycle_count"] == 1
    assert "remote unavailable" in str(status["last_error"])
    assert status["ordinary_dialogue_allowed"] is True


def test_busy_runtime_skips_non_forced_cycle(tmp_path) -> None:
    fake = _FakeSyncRuntime(MemorySyncMode.PUSH_PULL)
    controller = MemorySyncController(
        _cfg(tmp_path, mode="push_pull"),
        sync_runtime=fake,
        runtime_busy=lambda: True,
    )
    assert controller.tick(force=False) is None
    assert fake.calls == 0
    assert controller.status_payload()["state"] == "paused_runtime_busy"
    assert controller.status_payload()["skipped_busy_count"] == 1


def test_background_controller_runs_and_shutdown_is_bounded(tmp_path) -> None:
    fake = _FakeSyncRuntime(MemorySyncMode.BACKUP)
    controller = MemorySyncController(_cfg(tmp_path, mode="backup"), sync_runtime=fake)
    controller.start()
    assert fake.called.wait(0.5)
    controller.stop(join_timeout_seconds=0.5)
    status = controller.status_payload()
    assert fake.calls >= 1
    assert status["running"] is False
    assert status["state"] == "stopped"
