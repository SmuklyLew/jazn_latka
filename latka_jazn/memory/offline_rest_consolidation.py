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
    duplicate_groups: tuple[tuple[str, ...], ...]
    truth_status_counts: dict[str, int]
    status: str
    dream_generation_required: bool = False
    automatic_memory_promotion_allowed: bool = False
    schema_version: str = SCHEMA_VERSION
    truth_boundary: str = (
        "Offline rest consolidation is deterministic bookkeeping over already stored memory records. "
        "It does not create facts, does not invent experiences, does not train the base language model, "
        "and does not prove that a biological or conscious sleep state occurred."
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class OfflineRestConsolidator:
    """Perform useful rest work without invoking a language model.

    The consolidator deliberately avoids semantic invention. It checks replay integrity,
    source anchoring, provenance presence and exact duplicate content. Results are suitable
    for an auditable rest-cycle payload even when DreamSandbox is unavailable.
    """

    def run(self, replay_items: Iterable[RestReplayItem]) -> OfflineRestConsolidationReport:
        items = list(replay_items)
        truth_status_counts: dict[str, int] = {}
        source_anchor_count = 0
        inferred_or_symbolic_count = 0
        provenance_complete_count = 0
        content_hash_valid = True
        by_content_hash: dict[str, list[str]] = {}

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

            provenance = dict(item.provenance or {})
            if provenance and any(
                str(provenance.get(key) or "").strip()
                for key in (
                    "source_table",
                    "source_row_id",
                    "source_file",
                    "source_sha256",
                    "memory_record_content_sha256",
                    "normalized_content_hash",
                )
            ):
                provenance_complete_count += 1

        duplicate_groups = tuple(
            tuple(sorted(ids))
            for _content_hash, ids in sorted(by_content_hash.items())
            if len(ids) > 1
        )

        if not items:
            status = "completed_empty"
        elif not content_hash_valid:
            status = "integrity_failed"
        elif source_anchor_count == 0:
            status = "completed_without_real_source_anchor"
        else:
            status = "completed"

        return OfflineRestConsolidationReport(
            replay_count=len(items),
            source_anchor_count=source_anchor_count,
            inferred_or_symbolic_count=inferred_or_symbolic_count,
            content_hash_valid=content_hash_valid,
            provenance_complete_count=provenance_complete_count,
            duplicate_groups=duplicate_groups,
            truth_status_counts=truth_status_counts,
            status=status,
        )
