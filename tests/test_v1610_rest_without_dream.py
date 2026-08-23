from __future__ import annotations

from datetime import datetime, timezone

from latka_jazn.config import JaznConfig
from latka_jazn.core.rest_cycle_controller import RestCycleController
from latka_jazn.memory.dream_sandbox import DreamSandbox
from latka_jazn.memory.memory_tier_store import MemoryTierStore
from latka_jazn.memory.memory_tiers import MemoryKind, MemoryTruthStatus, ShortTermMemoryPolicy, SourceEvidence


def test_rest_without_dream_completes_offline_consolidation_and_keeps_dialogue_independent(tmp_path) -> None:
    config = JaznConfig(
        root=tmp_path,
        rest_local_model_enabled=False,
        rest_idle_start_seconds=1,
        rest_cycle_interval_seconds=1,
    )
    record = ShortTermMemoryPolicy().create(
        kind=MemoryKind.REFLECTION,
        content="Zweryfikowany rekord do model-free konsolidacji.",
        domain="test",
        mode="test",
        truth_status=MemoryTruthStatus.USER_CONFIRMED,
        confidence=0.9,
        importance=0.8,
        evidence=(SourceEvidence(source_type="test", source_id="source-1"),),
    )
    with MemoryTierStore(config.memory_tier_db_path) as store:
        store.save_record(record)

    now_ns = 3_000_000_000
    controller = RestCycleController(
        config,
        runtime_busy=lambda: False,
        dream=DreamSandbox(config),
        monotonic_ns=lambda: now_ns,
        utc_now=lambda: datetime(2026, 8, 23, tzinfo=timezone.utc).isoformat(),
    )
    try:
        result = controller.tick(force=True)
        assert result is not None
        assert result["status"] == "completed"
        assert result["completion_mode"] == "offline_consolidation_only"
        assert result["offline_rest_ready"] is True
        assert result["flow"] == ["replay", "offline_consolidation", "dream_unavailable"]
        assert controller.status_payload()["offline_rest_ready"] is True
    finally:
        controller.close()
