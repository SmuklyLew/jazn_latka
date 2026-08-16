from __future__ import annotations

from dataclasses import dataclass

from latka_jazn.core.rest_cycle_controller import RestCycleController
from latka_jazn.memory.offline_rest_consolidation import OfflineRestConsolidator
from latka_jazn.memory.rest_contracts import RestReplayItem, sha256_text


@dataclass
class _Config:
    rest_cycle_db_path: str = "unused.sqlite3"
    rest_cycle_enabled: bool = True
    rest_shadow_mode: bool = True
    rest_poll_seconds: float = 5.0
    rest_idle_start_seconds: float = 900.0
    rest_cycle_interval_seconds: float = 1800.0
    rest_max_cycles_per_episode: int = 16
    rest_replay_anti_loop_cycles: int = 4
    rest_replay_limit: int = 6


class _Store:
    path = "fake-rest.sqlite3"

    def __init__(self) -> None:
        self.finished: dict | None = None

    def recover_open_episode(self, **_kwargs):
        return None

    def active_episode(self):
        return {"episode_id": "episode-1"}

    def next_cycle_ordinal(self, _episode_id: str) -> int:
        return 1

    def begin_cycle(self, **_kwargs) -> str:
        return "cycle-1"

    def recent_replay_memory_ids(self, **_kwargs):
        return []

    def add_replay_item(self, *_args, **_kwargs) -> None:
        return None

    def update_cycle_phase(self, *_args, **_kwargs) -> None:
        return None

    def finish_cycle(self, cycle_id: str, **kwargs) -> None:
        self.finished = {"cycle_id": cycle_id, **kwargs}

    def close(self) -> None:
        return None


class _Replay:
    def select(self, **_kwargs):
        content = "Źródłowy zapis do replay."
        content_hash = sha256_text(content)
        return [
            RestReplayItem(
                source_memory_id="memory-1",
                source_tier="short_term",
                kind="episodic",
                truth_status="source_recorded",
                content=content,
                content_sha256=content_hash,
                domain="conversation",
                confidence=0.9,
                importance=0.8,
                score=0.8,
                provenance={
                    "source_table": "messages",
                    "source_row_id": "1",
                    "memory_record_content_sha256": content_hash,
                },
            )
        ]


class _NoDream:
    def generate(self, **_kwargs):
        return None, {"status": "not_configured"}

    def readiness(self):
        return {"rest_dream_ready": False, "status": "not_configured"}


class _NotCalled:
    def evaluate(self, *_args, **_kwargs):
        raise AssertionError("dream evaluation must not run without a scene")

    def decide(self, *_args, **_kwargs):
        raise AssertionError("dream consolidation must not run without a scene")


def test_rest_cycle_completes_offline_work_when_dream_model_is_unavailable() -> None:
    store = _Store()
    controller = RestCycleController(
        _Config(),
        store=store,
        replay=_Replay(),
        dream=_NoDream(),
        evaluator=_NotCalled(),
        consolidation=_NotCalled(),
        offline_consolidation=OfflineRestConsolidator(),
        monotonic_ns=lambda: 10_000_000_000,
        utc_now=lambda: "2026-08-16T12:00:00+00:00",
    )

    result = controller.tick(force=True)

    assert result is not None
    assert result["status"] == "completed"
    assert result["rest_mode"] == "offline_consolidation_only"
    assert result["dream_generated"] is False
    assert result["offline_consolidation_completed"] is True
    assert result["offline_consolidation"]["status"] == "completed"
    assert result["offline_consolidation"]["provenance_complete_count"] == 1
    assert result["offline_consolidation"]["provenance_missing_ids"] == ()
    assert store.finished is not None
    assert store.finished["status"] == "completed"
    assert store.finished["model_status"] == "not_configured"
