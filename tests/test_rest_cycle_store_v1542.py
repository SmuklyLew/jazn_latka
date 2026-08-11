from __future__ import annotations

import sqlite3

from latka_jazn.memory.rest_contracts import DreamScene, SimulationTruthStatus, sha256_text
from latka_jazn.memory.rest_cycle_store import RestCycleStore


def test_rest_store_integrity_and_database_constraints(tmp_path) -> None:
    path = tmp_path / "rest.sqlite3"
    with RestCycleStore(path) as store:
        episode = store.start_episode(
            trigger="test", continuity_mode="retrieval_only", continuity_claim_allowed=False,
            shadow_mode=True, started_at_utc="2026-08-11T20:00:00+00:00", started_monotonic_ns=1,
        )
        cycle = store.begin_cycle(
            episode_id=episode, ordinal=1, idle_seconds=900,
            started_at_utc="2026-08-11T20:15:00+00:00", started_monotonic_ns=2,
        )
        text = "Symulacja wewnętrzna."
        store.add_scene(DreamScene(
            scene_id="s1", cycle_id=cycle, simulation_kind=SimulationTruthStatus.SIMULATED_INTERNAL,
            content=text, content_sha256=sha256_text(text), source_memory_ids=(),
            generator_provider="test", generator_model="test", generator_status="completed",
            created_at_utc="2026-08-11T20:15:01+00:00",
        ), [])
        assert store.validate()["ok"] is True
        with store.transaction():
            try:
                store.con.execute("UPDATE dream_scenes SET factual_claim_allowed=1 WHERE scene_id='s1'")
            except sqlite3.IntegrityError:
                pass
            else:
                raise AssertionError("SQLite CHECK must reject factual dream scene")
