from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import hashlib
import json
import sqlite3
import zipfile

from latka_jazn.core.memory_search_planner import MemorySearchPlanner
from latka_jazn.memory.graph_aware_retrieval import GraphAwareRetrievalController
from latka_jazn.memory.living_memory_gateway import LivingMemoryGateway
from latka_jazn.tools.archive_import_provenance import (
    discover_archive_binding,
    persist_archive_binding,
    validate_persisted_archive_binding,
)
from latka_jazn.tools.memory_rebuild_app import UnifiedMemoryDatabase


def _conversation(identifier: str, text: str) -> dict:
    node_id = f"{identifier}-node"
    return {
        "id": identifier,
        "title": f"title-{identifier}",
        "create_time": 100.0,
        "update_time": 101.0,
        "current_node": node_id,
        "mapping": {
            node_id: {
                "id": node_id,
                "parent": None,
                "children": [],
                "message": {
                    "id": f"{identifier}-message",
                    "author": {"role": "user"},
                    "create_time": 100.0,
                    "content": {"content_type": "text", "parts": [text]},
                    "metadata": {},
                },
            }
        },
    }


def test_archive_sha_is_cryptographically_bound_to_extracted_import(tmp_path: Path) -> None:
    source = tmp_path / "conversations.json"
    source.write_text(
        json.dumps([_conversation("c1", "źródłowy dowód alpha")], ensure_ascii=False),
        encoding="utf-8",
    )
    database = tmp_path / "memory_jazn.sqlite3"
    result = UnifiedMemoryDatabase(database).import_source(source)
    assert result.status in {"imported", "already_imported", "completed"}

    archive = tmp_path / "chatgpt-export.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as output:
        output.writestr("conversations.json", source.read_bytes())
        output.writestr("unrelated.txt", b"not imported")

    discovered = discover_archive_binding(database, archive)
    assert discovered["ok"] is True
    assert discovered["matched_import_count"] == 1
    assert discovered["matches"][0]["proof_kind"] == "archive_member_sha256_exact"

    persisted = persist_archive_binding(database, discovered)
    assert persisted["ok"] is True
    assert persisted["binding_count"] == 1

    archive_sha = hashlib.sha256(archive.read_bytes()).hexdigest()
    verified = validate_persisted_archive_binding(database, archive_sha)
    assert verified["ok"] is True
    assert verified["binding_count"] == 1

    con = sqlite3.connect(database)
    try:
        source_row = con.execute(
            "SELECT kind,name FROM sources WHERE sha256=?",
            (archive_sha,),
        ).fetchone()
        link_row = con.execute(
            "SELECT source_record_id,target_record_id,relation,source_sha256 FROM links WHERE source_record_id=?",
            (archive_sha,),
        ).fetchone()
    finally:
        con.close()
    assert source_row is not None
    assert source_row[0] == "chatgpt_export_transport_archive"
    assert str(source_row[1]).startswith("archive:")
    assert link_row is not None
    assert link_row[0] == archive_sha
    assert link_row[2] == "cryptographically_contains_import_source"
    assert link_row[3] == archive_sha


def test_archive_binding_fails_closed_without_exact_archive_or_member_hash(tmp_path: Path) -> None:
    source = tmp_path / "conversations.json"
    source.write_text(
        json.dumps([_conversation("c1", "źródłowy dowód alpha")], ensure_ascii=False),
        encoding="utf-8",
    )
    database = tmp_path / "memory_jazn.sqlite3"
    UnifiedMemoryDatabase(database).import_source(source)

    unrelated = tmp_path / "different.zip"
    with zipfile.ZipFile(unrelated, "w", compression=zipfile.ZIP_DEFLATED) as output:
        output.writestr("conversations.json", b"[]")

    discovered = discover_archive_binding(database, unrelated)
    assert discovered["ok"] is False
    assert discovered["matched_import_count"] == 0


def _hit(
    record_id: str,
    conversation_id: str,
    text: str,
    relevance: float,
) -> SimpleNamespace:
    return SimpleNamespace(
        record_id=record_id,
        source_locator=f"{conversation_id}:node:{record_id}",
        title="",
        content_excerpt=text,
        relevance=relevance,
        truth_status="source_recorded",
        metadata={"conversation_id": conversation_id, "query_pass": "focus"},
    )


def test_graph_candidate_never_promotes_zero_focus_hit_for_diversity() -> None:
    controller = GraphAwareRetrievalController(max_per_conversation=1)
    hits = [
        _hit("a1", "conv-a", "alpha właściwy dowód", 0.95),
        _hit("a2", "conv-a", "alpha drugi właściwy dowód", 0.93),
        _hit("wrong", "conv-b", "zupełnie obca rozmowa", 0.92),
        _hit("c1", "conv-c", "alpha trzeci właściwy dowód", 0.82),
    ]

    decision = controller.select(
        hits,
        query="alpha",
        focus_terms=["alpha"],
        limit=3,
        mode="active",
    )

    assert [item.record_id for item in decision.selected] == ["a1", "a2", "c1"]
    assert decision.telemetry["zero_coverage_promotion_count"] == 0
    assert decision.telemetry["promotion_requires_focus_coverage"] is True


def test_referential_followup_uses_previous_query_as_fts_focus(tmp_path: Path) -> None:
    planner = MemorySearchPlanner(tmp_path)
    followup = planner.plan(
        "Wróć do tego wspomnienia i doprecyzuj źródło.",
        previous_query="Przypomnij alphaunikalna Katedra",
    )
    assert followup.search_mode == "referential_followup"

    gateway = LivingMemoryGateway(tmp_path)
    effective = gateway._referential_plan(followup)
    normalized = {str(item).casefold() for item in effective.focus_terms}

    assert "alphaunikalna" in normalized
    assert "katedra" in normalized
    assert "wróć" not in normalized
    assert "doprecyzuj" not in normalized
    assert "źródło" not in normalized
