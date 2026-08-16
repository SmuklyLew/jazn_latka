from __future__ import annotations

from latka_jazn.memory.offline_rest_consolidation import OfflineRestConsolidator
from latka_jazn.memory.rest_contracts import RestReplayItem, sha256_text


def _item(
    memory_id: str,
    content: str,
    *,
    truth: str = "source_recorded",
    complete_provenance: bool = True,
) -> RestReplayItem:
    content_hash = sha256_text(content)
    provenance = {"source_table": "messages", "source_row_id": memory_id}
    if complete_provenance:
        provenance["memory_record_content_sha256"] = content_hash
    return RestReplayItem(
        source_memory_id=memory_id,
        source_tier="short_term",
        kind="episodic",
        truth_status=truth,
        content=content,
        content_sha256=content_hash,
        domain="conversation",
        confidence=0.9,
        importance=0.8,
        score=0.7,
        provenance=provenance,
    )


def test_offline_rest_runs_without_dream_generation() -> None:
    report = OfflineRestConsolidator().run([
        _item("m1", "Pierwsze wspomnienie."),
        _item("m2", "Drugie wspomnienie."),
    ])

    assert report.status == "completed"
    assert report.replay_count == 2
    assert report.source_anchor_count == 2
    assert report.provenance_complete_count == 2
    assert report.provenance_missing_ids == ()
    assert report.dream_generation_required is False
    assert report.automatic_memory_promotion_allowed is False
    assert report.content_hash_valid is True


def test_offline_rest_marks_incomplete_source_provenance_without_inventing_evidence() -> None:
    report = OfflineRestConsolidator().run([
        _item("m1", "Źródłowy zapis bez hasha provenance.", complete_provenance=False),
    ])

    assert report.status == "completed_with_incomplete_provenance"
    assert report.source_anchor_count == 1
    assert report.provenance_complete_count == 0
    assert report.provenance_missing_ids == ("m1",)
    assert report.content_hash_valid is True


def test_offline_rest_detects_exact_duplicate_content_without_inventing_semantics() -> None:
    content = "Ten sam zapis źródłowy."
    report = OfflineRestConsolidator().run([
        _item("m1", content),
        _item("m2", content),
    ])

    assert report.duplicate_groups == (("m1", "m2"),)


def test_offline_rest_reports_lack_of_real_source_anchor() -> None:
    report = OfflineRestConsolidator().run([
        _item("m1", "Wniosek systemu.", truth="inferred"),
    ])

    assert report.status == "completed_without_real_source_anchor"
    assert report.source_anchor_count == 0
    assert report.inferred_or_symbolic_count == 1


def test_empty_replay_is_a_completed_empty_housekeeping_pass() -> None:
    report = OfflineRestConsolidator().run([])

    assert report.status == "completed_empty"
    assert report.replay_count == 0
