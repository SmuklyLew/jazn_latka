from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
import math

from latka_jazn.config import JaznConfig
from latka_jazn.memory.memory_tier_store import MemoryTierStore
from latka_jazn.memory.memory_tiers import MemoryKind, MemoryRecord, MemoryTier, MemoryTruthStatus
from latka_jazn.memory.rest_contracts import RestReplayItem, sha256_text
from latka_jazn.version import schema_version

SCHEMA_VERSION = schema_version("rest_replay")

_ALLOWED_TRUTH = {
    MemoryTruthStatus.SOURCE_RECORDED,
    MemoryTruthStatus.USER_CONFIRMED,
    MemoryTruthStatus.INFERRED,
    MemoryTruthStatus.SYMBOLIC,
    MemoryTruthStatus.CANONICAL,
}
_REAL_SOURCE_TRUTH = {
    MemoryTruthStatus.SOURCE_RECORDED,
    MemoryTruthStatus.USER_CONFIRMED,
    MemoryTruthStatus.CANONICAL,
}
_KIND_BONUS = {
    MemoryKind.OPEN_TASK: 0.18,
    MemoryKind.REFLECTION: 0.15,
    MemoryKind.PROCEDURAL: 0.14,
    MemoryKind.EPISODIC: 0.12,
    MemoryKind.PREFERENCE: 0.10,
    MemoryKind.SEMANTIC: 0.09,
    MemoryKind.CONVERSATION_CONTEXT: 0.06,
}


def _recency_score(updated_at: datetime, *, now: datetime) -> float:
    age_seconds = max(0.0, (now - updated_at.astimezone(timezone.utc)).total_seconds())
    # Half-life of roughly one week, bounded so old but important memories remain eligible.
    return max(0.05, min(1.0, math.exp(-age_seconds / (7.0 * 86400.0))))


class RestReplayEngine:
    """Select a small, source-grounded replay set without writing to memory.

    The selector reads canonical L1/L2/L3 records and returns bounded excerpts to the
    dream sandbox. Rejected/draft/book-scene records are not eligible. Recently replayed
    records receive a penalty so one high-importance memory cannot monopolize every cycle.
    """

    def __init__(self, config: JaznConfig) -> None:
        self.config = config
        self.tier_path = Path(config.memory_tier_db_path)

    @staticmethod
    def is_real_source_anchor(item: RestReplayItem) -> bool:
        return item.truth_status in {status.value for status in _REAL_SOURCE_TRUTH}

    def select(
        self,
        *,
        limit: int = 6,
        recent_memory_ids: Iterable[str] = (),
        now: datetime | None = None,
    ) -> list[RestReplayItem]:
        if limit <= 0 or not self.tier_path.is_file():
            return []
        current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        recent = {str(value) for value in recent_memory_ids}
        with MemoryTierStore(self.tier_path) as store:
            records = store.list_records()

        candidates: list[tuple[float, MemoryRecord]] = []
        for record in records:
            if record.truth_status not in _ALLOWED_TRUTH:
                continue
            if record.tier is MemoryTier.WORKING and not getattr(record, "checkpoint_allowed", False):
                continue
            if isinstance(record.content, str) and not record.content.strip():
                continue
            truth_bonus = 0.15 if record.truth_status in _REAL_SOURCE_TRUTH else 0.04
            tier_bonus = {
                MemoryTier.LONG_TERM: 0.12,
                MemoryTier.SHORT_TERM: 0.10,
                MemoryTier.WORKING: 0.06,
            }.get(record.tier, 0.0)
            score = (
                0.30 * float(record.importance)
                + 0.20 * float(record.confidence)
                + 0.18 * _recency_score(record.updated_at_utc, now=current)
                + _KIND_BONUS.get(record.kind, 0.05)
                + truth_bonus
                + tier_bonus
            )
            if record.memory_id in recent:
                score -= 0.28
            candidates.append((max(0.0, min(1.0, score)), record))

        candidates.sort(key=lambda pair: (pair[0], pair[1].updated_at_utc, pair[1].memory_id), reverse=True)
        selected: list[RestReplayItem] = []
        domain_counts: dict[str, int] = {}
        kind_counts: dict[str, int] = {}
        selected_ids: set[str] = set()
        diversity_cap = max(1, (int(limit) + 1) // 2)

        def append_record(score: float, record: MemoryRecord) -> None:
            domain = str(record.domain or "unknown")
            kind = record.kind.value
            content = str(record.content)[:2400]
            selected.append(
                RestReplayItem(
                    source_memory_id=record.memory_id,
                    source_tier=record.tier.value,
                    kind=kind,
                    truth_status=record.truth_status.value,
                    content=content,
                    content_sha256=sha256_text(content),
                    domain=domain,
                    confidence=float(record.confidence),
                    importance=float(record.importance),
                    score=score,
                    provenance={
                        "memory_record_content_sha256": record.content_sha256,
                        "source_evidence_keys": [item.evidence_key for item in record.evidence],
                        "record_updated_at_utc": record.updated_at_utc.isoformat(),
                        "read_only": True,
                        "rest_replay_schema_version": SCHEMA_VERSION,
                    },
                )
            )
            selected_ids.add(record.memory_id)
            domain_counts[domain] = domain_counts.get(domain, 0) + 1
            kind_counts[kind] = kind_counts.get(kind, 0) + 1

        # First pass maximizes diversity. Second pass fills the bounded budget so a
        # homogeneous but valid memory set does not collapse to a single item.
        for score, record in candidates:
            if len(selected) >= int(limit):
                break
            domain = str(record.domain or "unknown")
            kind = record.kind.value
            if domain_counts.get(domain, 0) >= diversity_cap or kind_counts.get(kind, 0) >= diversity_cap:
                continue
            append_record(score, record)
        if len(selected) < int(limit):
            for score, record in candidates:
                if len(selected) >= int(limit):
                    break
                if record.memory_id in selected_ids:
                    continue
                append_record(score, record)
        return selected
