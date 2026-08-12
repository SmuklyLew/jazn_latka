from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Any
import json
import math
import sqlite3

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
        self.sidecar_path = Path(config.normalization_sidecar_db_path)

    @staticmethod
    def is_real_source_anchor(item: RestReplayItem) -> bool:
        return item.truth_status in {status.value for status in _REAL_SOURCE_TRUTH}

    @staticmethod
    def _sidecar_truth(value: str) -> str:
        low = str(value or "").strip().lower()
        if low in {"source_recorded", "source_recorded_pending_review", "recovered_from_legacy_source", "curated_memory_record", "runtime_rule_record", "truth_boundary_record"}:
            return MemoryTruthStatus.SOURCE_RECORDED.value
        if low in {"semantic_claim_with_confidence", "reflection_record"}:
            return MemoryTruthStatus.INFERRED.value
        if "symbolic" in low or "book_scene" in low:
            return MemoryTruthStatus.SYMBOLIC.value
        return MemoryTruthStatus.INFERRED.value

    @staticmethod
    def _sidecar_kind(value: str) -> str:
        low = str(value or "").strip().lower()
        if "proced" in low or "rule" in low or "truth_audit" in low:
            return MemoryKind.PROCEDURAL.value
        if "reflect" in low:
            return MemoryKind.REFLECTION.value
        if "episod" in low or "journal" in low or "message" in low or "conversation" in low:
            return MemoryKind.EPISODIC.value
        if "semantic" in low or "fact" in low:
            return MemoryKind.SEMANTIC.value
        return MemoryKind.CONVERSATION_CONTEXT.value

    def _normalized_candidates(self, *, now: datetime, recent: set[str]) -> list[RestReplayItem]:
        if not self.sidecar_path.is_file():
            return []
        try:
            uri = f"file:{self.sidecar_path.as_posix()}?mode=ro&immutable=1"
            with sqlite3.connect(uri, uri=True) as con:
                con.row_factory = sqlite3.Row
                run = con.execute(
                    "SELECT run_id FROM normalization_runs WHERE status='ok' AND coverage_complete=1 ORDER BY ended_at_utc DESC, started_at_utc DESC LIMIT 1"
                ).fetchone()
                if not run:
                    return []
                rows = con.execute(
                    """
                    SELECT item_id,memory_type,source_table,source_row_id,conversation_id,message_id,
                           source_timestamp,source_file,source_sha256,content_excerpt,content_hash,
                           truth_status,confidence,importance,memory_namespace,source_evidence_json,
                           updated_at_utc,run_id
                      FROM normalized_memory_items
                     WHERE run_id=? AND trim(content_excerpt)<>''
                     ORDER BY importance DESC, confidence DESC, COALESCE(source_timestamp, updated_at_utc) DESC
                     LIMIT 512
                    """,
                    (str(run[0]),),
                ).fetchall()
        except sqlite3.Error:
            return []

        out: list[RestReplayItem] = []
        for row in rows:
            item_id = str(row["item_id"])
            truth = self._sidecar_truth(str(row["truth_status"] or ""))
            kind = self._sidecar_kind(str(row["memory_type"] or ""))
            content = str(row["content_excerpt"] or "")[:2400]
            if not content.strip():
                continue
            timestamp = str(row["source_timestamp"] or row["updated_at_utc"] or "")
            try:
                updated = datetime.fromisoformat(timestamp.replace("Z", "+00:00")) if timestamp else now
                if updated.tzinfo is None:
                    updated = updated.replace(tzinfo=timezone.utc)
            except ValueError:
                updated = now
            truth_bonus = 0.15 if truth == MemoryTruthStatus.SOURCE_RECORDED.value else 0.04
            kind_bonus = {
                MemoryKind.PROCEDURAL.value: 0.14,
                MemoryKind.REFLECTION.value: 0.15,
                MemoryKind.EPISODIC.value: 0.12,
                MemoryKind.SEMANTIC.value: 0.09,
                MemoryKind.CONVERSATION_CONTEXT.value: 0.06,
            }.get(kind, 0.05)
            score = (
                0.30 * float(row["importance"] or 0.0)
                + 0.20 * float(row["confidence"] or 0.0)
                + 0.18 * _recency_score(updated, now=now)
                + kind_bonus + truth_bonus + 0.10
            )
            if item_id in recent:
                score -= 0.28
            try:
                evidence = json.loads(str(row["source_evidence_json"] or "{}"))
            except json.JSONDecodeError:
                evidence = {}
            out.append(RestReplayItem(
                source_memory_id=item_id,
                source_tier="normalized_l1",
                kind=kind,
                truth_status=truth,
                content=content,
                content_sha256=sha256_text(content),
                domain=str(row["memory_namespace"] or "recovered_memory"),
                confidence=float(row["confidence"] or 0.0),
                importance=float(row["importance"] or 0.0),
                score=max(0.0, min(1.0, score)),
                provenance={
                    "normalized_content_hash": str(row["content_hash"] or ""),
                    "source_table": str(row["source_table"] or ""),
                    "source_row_id": str(row["source_row_id"] or ""),
                    "conversation_id": str(row["conversation_id"] or ""),
                    "message_id": str(row["message_id"] or ""),
                    "source_file": str(row["source_file"] or ""),
                    "source_sha256": str(row["source_sha256"] or ""),
                    "source_evidence": evidence,
                    "normalization_run_id": str(row["run_id"] or ""),
                    "read_only": True,
                    "rest_replay_schema_version": SCHEMA_VERSION,
                },
            ))
        return out

    def _tier_candidates(self, *, now: datetime, recent: set[str]) -> list[RestReplayItem]:
        if not self.tier_path.is_file():
            return []
        with MemoryTierStore(self.tier_path) as store:
            records = store.list_records()
        out: list[RestReplayItem] = []
        for record in records:
            if record.truth_status not in _ALLOWED_TRUTH:
                continue
            if record.tier is MemoryTier.WORKING and not getattr(record, "checkpoint_allowed", False):
                continue
            if isinstance(record.content, str) and not record.content.strip():
                continue
            truth_bonus = 0.15 if record.truth_status in _REAL_SOURCE_TRUTH else 0.04
            tier_bonus = {MemoryTier.LONG_TERM: 0.12, MemoryTier.SHORT_TERM: 0.10, MemoryTier.WORKING: 0.06}.get(record.tier, 0.0)
            score = (
                0.30 * float(record.importance)
                + 0.20 * float(record.confidence)
                + 0.18 * _recency_score(record.updated_at_utc, now=now)
                + _KIND_BONUS.get(record.kind, 0.05) + truth_bonus + tier_bonus
            )
            # A wake-state aggregate is useful context but must not monopolize replay
            # when individual normalized source records are available.
            if str(getattr(record, "mode", "")) == "wake_state":
                score -= 0.22
            if record.memory_id in recent:
                score -= 0.28
            content = str(record.content)[:2400]
            out.append(RestReplayItem(
                source_memory_id=record.memory_id,
                source_tier=record.tier.value,
                kind=record.kind.value,
                truth_status=record.truth_status.value,
                content=content,
                content_sha256=sha256_text(content),
                domain=str(record.domain or "unknown"),
                confidence=float(record.confidence),
                importance=float(record.importance),
                score=max(0.0, min(1.0, score)),
                provenance={
                    "memory_record_content_sha256": record.content_sha256,
                    "source_evidence_keys": [item.evidence_key for item in record.evidence],
                    "record_updated_at_utc": record.updated_at_utc.isoformat(),
                    "record_mode": str(getattr(record, "mode", "")),
                    "read_only": True,
                    "rest_replay_schema_version": SCHEMA_VERSION,
                },
            ))
        return out

    def select(
        self,
        *,
        limit: int = 6,
        recent_memory_ids: Iterable[str] = (),
        now: datetime | None = None,
    ) -> list[RestReplayItem]:
        if limit <= 0:
            return []
        current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        recent = {str(value) for value in recent_memory_ids}
        candidates = self._normalized_candidates(now=current, recent=recent)
        candidates.extend(self._tier_candidates(now=current, recent=recent))
        # Deduplicate source ids and favor higher-scored independently normalized records.
        best: dict[str, RestReplayItem] = {}
        for item in candidates:
            previous = best.get(item.source_memory_id)
            if previous is None or item.score > previous.score:
                best[item.source_memory_id] = item
        ordered = sorted(best.values(), key=lambda item: (item.score, item.importance, item.confidence, item.source_memory_id), reverse=True)

        selected: list[RestReplayItem] = []
        domain_counts: dict[str, int] = {}
        kind_counts: dict[str, int] = {}
        diversity_cap = max(1, (int(limit) + 1) // 2)
        for item in ordered:
            if len(selected) >= int(limit):
                break
            if domain_counts.get(item.domain, 0) >= diversity_cap or kind_counts.get(item.kind, 0) >= diversity_cap:
                continue
            selected.append(item)
            domain_counts[item.domain] = domain_counts.get(item.domain, 0) + 1
            kind_counts[item.kind] = kind_counts.get(item.kind, 0) + 1
        if len(selected) < int(limit):
            selected_ids = {item.source_memory_id for item in selected}
            for item in ordered:
                if len(selected) >= int(limit):
                    break
                if item.source_memory_id in selected_ids:
                    continue
                selected.append(item)
                selected_ids.add(item.source_memory_id)
        return selected
