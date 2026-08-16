from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable

from latka_jazn.memory.rest_contracts import RestReplayItem, sha256_text
from latka_jazn.version import schema_version

SCHEMA_VERSION = schema_version("offline_rest_consolidation")

_REAL_SOURCE_TRUTH = {"source_recorded", "user_confirmed", "canonical"}


@dataclass(slots=True, frozen=True)
class OfflineRestConsolidationReport:
    replay_count: int
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
        "It detects exact duplicates, integrity failures and provenance collisions, but it does not invent semantic contradictions, "
        "create facts, train the base language model, or prove biological/conscious sleep."
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class OfflineRestConsolidator:
    """Perform useful, model-free rest work over replayed memory records.

    The consolidator never asks an LLM to decide truth. It validates content hashes,
    classifies source anchors, verifies bounded provenance, detects exact duplicate
    content and flags cases where one source identity points at conflicting content.
    Those conflict groups are candidates for later review, not automatic corrections.
    """

    @staticmethod
    def _source_identity(item: RestReplayItem) -> str:
        provenance = dict(item.provenance or {})
        source_table = str(provenance.get("source_table") or "").strip()
        source_row = str(provenance.get("source_row_id") or "").strip()
        if source_table and source_row:
            return f"table:{source_table}:{source_row}"
        source_file = str(provenance.get("source_file") or "").strip()
        source_sha = str(provenance.get("source_sha256") or "").strip()
        if source_file and source_sha:
            return f"file:{source_file}:{source_sha}"
        record_sha = str(provenance.get("memory_record_content_sha256") or "").strip()
        if record_sha:
            return f"record:{item.source_memory_id}:{record_sha}"
        return f"memory:{item.source_memory_id}"

    @staticmethod
    def _provenance_complete(item: RestReplayItem) -> bool:
        provenance = dict(item.provenance or {})
        if not provenance:
            return False
        locator = any(
            str(provenance.get(key) or "").strip()
            for key in ("source_row_id", "source_file", "memory_record_content_sha256", "normalized_content_hash")
        )
        integrity = any(
            str(provenance.get(key) or "").strip()
            for key in ("source_sha256", "memory_record_content_sha256", "normalized_content_hash")
        )
        return locator and integrity

    def run(self, replay_items: Iterable[RestReplayItem]) -> OfflineRestConsolidationReport:
        items = list(replay_items)
        truth_status_counts: dict[str, int] = {}
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
            if truth in _REAL_SOURCE_TRUTH:
                source_anchor_count += 1
            else:
                inferred_or_symbolic_count += 1

            computed_hash = sha256_text(item.content)
            if computed_hash != item.content_sha256:
                content_hash_valid = False
            by_content_hash.setdefault(computed_hash, []).append(item.source_memory_id)

            identity = self._source_identity(item)
            by_source_identity.setdefault(identity, []).append((item.source_memory_id, computed_hash))

            if self._provenance_complete(item):
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
            status = "completed_without_real_source_anchor"
        elif provenance_missing_ids:
            status = "completed_with_incomplete_provenance"
        else:
            status = "completed"

        return OfflineRestConsolidationReport(
            replay_count=len(items),
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
