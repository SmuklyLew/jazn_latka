from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable

from latka_jazn.memory.memory_promotion_gate import MemoryPromotionGate
from latka_jazn.memory.rest_contracts import RestReplayItem, sha256_text
from latka_jazn.memory.rest_replay import RestReplayEngine
from latka_jazn.version import schema_version


SCHEMA_VERSION = schema_version("offline_rest_consolidation")


@dataclass(slots=True, frozen=True)
class OfflineRestConsolidationReport:
    replay_count: int
    truth_eligible_source_count: int
    source_anchor_count: int
    inferred_or_symbolic_count: int
    content_hash_valid: bool
    provenance_complete_count: int
    provenance_missing_ids: tuple[str, ...]
    duplicate_groups: tuple[tuple[str, ...], ...]
    source_conflict_groups: tuple[tuple[str, ...], ...]
    truth_status_counts: dict[str, int]
    unique_content_count: int
    unique_source_identity_count: int
    status: str
    dream_generation_required: bool = False
    automatic_memory_promotion_allowed: bool = False
    schema_version: str = SCHEMA_VERSION
    truth_boundary: str = (
        "Offline rest consolidation is deterministic bookkeeping over already stored memory records. "
        "It validates hashes and provenance and detects exact duplicates or source collisions; it does not "
        "invent facts, infer semantic contradictions, train the base model, or prove dreaming."
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class OfflineRestConsolidator:
    """Perform useful, bounded and model-free work over replayed records."""

    @staticmethod
    def _source_identity(item: RestReplayItem) -> str | None:
        return MemoryPromotionGate._source_identity(item)

    def run(self, replay_items: Iterable[RestReplayItem]) -> OfflineRestConsolidationReport:
        items = list(replay_items)
        truth_status_counts: dict[str, int] = {}
        truth_eligible_source_count = 0
        source_anchor_count = 0
        inferred_or_symbolic_count = 0
        provenance_complete_count = 0
        provenance_missing_ids: list[str] = []
        content_hash_valid = True
        by_content_hash: dict[str, list[str]] = {}
        by_source_identity: dict[str, list[tuple[str, str]]] = {}

        for item in items:
            truth = str(item.truth_status or "unknown")
            truth_status_counts[truth] = truth_status_counts.get(truth, 0) + 1
            if RestReplayEngine.is_real_source_anchor(item):
                truth_eligible_source_count += 1
            else:
                inferred_or_symbolic_count += 1

            computed_hash = sha256_text(item.content)
            if computed_hash != item.content_sha256:
                content_hash_valid = False
            by_content_hash.setdefault(computed_hash, []).append(item.source_memory_id)

            identity = self._source_identity(item)
            if identity:
                by_source_identity.setdefault(identity, []).append((item.source_memory_id, computed_hash))

            if MemoryPromotionGate.is_verified_source_anchor(item):
                source_anchor_count += 1
                provenance_complete_count += 1
            else:
                provenance_missing_ids.append(item.source_memory_id)

        duplicate_groups = tuple(
            tuple(sorted(ids))
            for _content_hash, ids in sorted(by_content_hash.items())
            if len(ids) > 1
        )
        source_conflict_groups = tuple(
            tuple(sorted(memory_id for memory_id, _hash in members))
            for _identity, members in sorted(by_source_identity.items())
            if len({content_hash for _memory_id, content_hash in members}) > 1
        )

        if not items:
            status = "completed_empty"
        elif not content_hash_valid:
            status = "integrity_failed"
        elif source_conflict_groups:
            status = "completed_with_source_conflicts"
        elif source_anchor_count == 0:
            status = "completed_without_verified_source_anchor"
        elif provenance_missing_ids:
            status = "completed_with_incomplete_provenance"
        else:
            status = "completed"

        return OfflineRestConsolidationReport(
            replay_count=len(items),
            truth_eligible_source_count=truth_eligible_source_count,
            source_anchor_count=source_anchor_count,
            inferred_or_symbolic_count=inferred_or_symbolic_count,
            content_hash_valid=content_hash_valid,
            provenance_complete_count=provenance_complete_count,
            provenance_missing_ids=tuple(sorted(provenance_missing_ids)),
            duplicate_groups=duplicate_groups,
            source_conflict_groups=source_conflict_groups,
            truth_status_counts=truth_status_counts,
            unique_content_count=len(by_content_hash),
            unique_source_identity_count=len(by_source_identity),
            status=status,
        )
