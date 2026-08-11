from __future__ import annotations

from latka_jazn.config import JaznConfig
from latka_jazn.memory.memory_tier_store import MemoryTierStore
from latka_jazn.memory.memory_tiers import MemoryKind, MemoryTruthStatus, ShortTermMemoryPolicy, SourceEvidence
from latka_jazn.memory.rest_replay import RestReplayEngine


def _seed(config: JaznConfig, *, suffix: str, truth: MemoryTruthStatus = MemoryTruthStatus.USER_CONFIRMED) -> str:
    record = ShortTermMemoryPolicy().create(
        kind=MemoryKind.REFLECTION,
        content=f"Zweryfikowany materiał źródłowy {suffix}",
        domain=f"domain-{suffix}", mode="test", truth_status=truth,
        confidence=0.9, importance=0.9,
        evidence=(SourceEvidence(source_type="test", source_id=f"src-{suffix}"),),
    )
    with MemoryTierStore(config.memory_tier_db_path) as store:
        store.save_record(record)
    return record.memory_id


def test_replay_is_bounded_source_grounded_and_penalizes_recent(tmp_path) -> None:
    config = JaznConfig(root=tmp_path)
    first = _seed(config, suffix="a")
    second = _seed(config, suffix="b")
    items = RestReplayEngine(config).select(limit=2, recent_memory_ids={first})
    assert len(items) == 2
    assert {item.source_memory_id for item in items} == {first, second}
    scores = {item.source_memory_id: item.score for item in items}
    assert scores[second] > scores[first]
    assert all(item.provenance["read_only"] is True for item in items)
