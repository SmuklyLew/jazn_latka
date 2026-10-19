from __future__ import annotations

from latka_jazn.config import JaznConfig
from latka_jazn.memory.rest_cycle_store import RestCycleStore
from latka_jazn.memory.rest_wake_report import RestWakeReportBuilder
from latka_jazn.memory.wake_state_runtime import WakeStateRuntimeBridge


def test_rest_report_survives_when_verified_wake_is_unavailable(tmp_path) -> None:
    config = JaznConfig(root=tmp_path)
    with RestCycleStore(config.rest_cycle_db_path) as store:
        episode = store.start_episode(
            trigger="test", continuity_mode="retrieval_only", continuity_claim_allowed=False,
            shadow_mode=True, started_at_utc="2026-08-11T20:00:00+00:00", started_monotonic_ns=1,
        )
        store.finish_episode(
            episode, status="completed", ended_at_utc="2026-08-11T21:00:00+00:00", ended_monotonic_ns=3_600_000_000_001,
        )
        RestWakeReportBuilder(store).build_and_persist(episode)

    status = WakeStateRuntimeBridge(config).load()
    assert status.status == "sidecar_missing"
    assert status.continuity_claim_allowed is False
    assert status.rest_continuity_status == "rest_verified"
    assert status.rest_report is not None
    assert status.rest_report["cycle_count"] == 0
