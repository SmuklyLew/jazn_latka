from __future__ import annotations

from latka_jazn.memory.rest_cycle_store import RestCycleStore
from latka_jazn.memory.rest_wake_report import RestWakeReportBuilder, load_latest_rest_wake_report


def test_verified_rest_report_survives_reopen_and_detects_tampering(tmp_path) -> None:
    path = tmp_path / "rest.sqlite3"
    with RestCycleStore(path) as store:
        episode = store.start_episode(
            trigger="test", continuity_mode="retrieval_only", continuity_claim_allowed=False,
            shadow_mode=True, started_at_utc="2026-08-11T20:00:00+00:00", started_monotonic_ns=100,
        )
        cycle = store.begin_cycle(
            episode_id=episode, ordinal=1, idle_seconds=900,
            started_at_utc="2026-08-11T20:15:00+00:00", started_monotonic_ns=200,
        )
        store.finish_cycle(
            cycle, status="skipped", ended_at_utc="2026-08-11T20:15:01+00:00", ended_monotonic_ns=300,
            phase_reached=3, model_status="model_unavailable", error=None, payload={"reason": "model_unavailable"},
        )
        store.finish_episode(
            episode, status="completed", ended_at_utc="2026-08-11T21:00:00+00:00", ended_monotonic_ns=3_600_000_000_100,
        )
        report = RestWakeReportBuilder(store).build_and_persist(episode)
        assert report["rest_continuity_status"] == "rest_verified"
        assert report["cycle_count"] == 1
        assert report["report_sha256"]

    loaded = load_latest_rest_wake_report(path)
    assert loaded["rest_continuity_status"] == "rest_verified"
    assert loaded["report_sha256"] == report["report_sha256"]

    with RestCycleStore(path) as store:
        with store.transaction():
            store.con.execute("UPDATE rest_wake_reports SET report_json='{}'")
    tampered = load_latest_rest_wake_report(path)
    assert tampered["rest_continuity_status"] == "rest_integrity_failed"
