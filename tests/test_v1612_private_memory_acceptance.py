from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import json

from latka_jazn.memory.living_memory_gateway import LivingMemoryGateway
from latka_jazn.tools.memory_rebuild_app import UnifiedMemoryDatabase
from latka_jazn.tools.private_memory_acceptance import run_acceptance


def _conversation(identifier: str, text: str) -> dict:
    node = f"{identifier}-node"
    return {
        "id": identifier,
        "title": f"title-{identifier}",
        "create_time": 100.0,
        "update_time": 101.0,
        "current_node": node,
        "mapping": {
            node: {
                "id": node,
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


def _database(tmp_path: Path) -> Path:
    source = tmp_path / "conversations.json"
    source.write_text(
        json.dumps([
            _conversation("relevant", "sekretnytermatesty alphaunikalna"),
            _conversation("wrong", "częsty wspólny tekst bez właściwego dowodu"),
        ], ensure_ascii=False),
        encoding="utf-8",
    )
    database = tmp_path / "memory_jazn.sqlite3"
    result = UnifiedMemoryDatabase(database).import_source(source)
    assert result.status in {"imported", "already_imported", "completed"}
    return database


def test_gateway_prefers_focus_terms_and_global_relevance(tmp_path: Path) -> None:
    database = _database(tmp_path)
    plan = SimpleNamespace(
        search_mode="semantic_query",
        focus_terms=["alphaunikalna"],
        search_terms=["wspólny", "tekst", "alphaunikalna"],
    )

    result = LivingMemoryGateway(database).search(plan, limit=2)

    assert result["hits"]
    assert result["hits"][0]["record_id"] == "relevant-node"


def test_private_acceptance_persists_no_private_query_or_content(tmp_path: Path) -> None:
    database = _database(tmp_path)
    cases = tmp_path / "recall.private.json"
    cases.write_text(
        json.dumps({
            "schema_version": "jazn_private_recall_cases/v1",
            "minimums": {},
            "source_files": ["private-source"],
            "recall_cases": [{
                "id": "private-case",
                "query": "Przypomnij alphaunikalna",
                "expected_any": ["sekretnytermatesty"],
                "expected_all": [],
                "forbidden_any": ["nieistniejacyzakaz"],
                "expected_sources": ["archive_chats"],
                "minimum_hits": 1,
                "limit": 10,
            }],
        }, ensure_ascii=False),
        encoding="utf-8",
    )

    report = run_acceptance(database, cases)
    serialized = json.dumps(report, ensure_ascii=False)

    assert report["ok"] is True
    assert report["recall"]["evidence_recall_at_k"]["10"] == 1.0
    assert report["recall"]["abstention"]["ok"] is True
    assert report["private_content_persisted"] is False
    assert "Przypomnij alphaunikalna" not in serialized
    assert "sekretnytermatesty" not in serialized


def test_private_acceptance_fails_closed_on_source_manifest_hash_mismatch(tmp_path: Path) -> None:
    database = _database(tmp_path)
    cases = tmp_path / "recall.private.json"
    cases.write_text(
        json.dumps({
            "schema_version": "jazn_private_recall_cases/v1",
            "recall_cases": [{
                "id": "private-case",
                "query": "alphaunikalna",
                "expected_any": ["sekretnytermatesty"],
                "expected_all": [],
                "expected_sources": ["archive_chats"],
                "minimum_hits": 1,
                "limit": 10,
            }],
        }),
        encoding="utf-8",
    )
    different = tmp_path / "different.zip"
    different.write_bytes(b"not-the-imported-source")
    manifest = tmp_path / "source-manifest.private.json"
    manifest.write_text(
        json.dumps({
            "operator_attestation": {
                "all_known_chatgpt_exports_included": True,
                "latest_export_created_immediately_before_test": True,
                "source_order_reviewed": True,
            },
            "sources": [{
                "ordinal": 1,
                "path": str(different),
                "approved": True,
                "latest_export": True,
            }],
        }),
        encoding="utf-8",
    )

    report = run_acceptance(database, cases, source_manifest=manifest)

    assert report["ok"] is False
    assert report["source_inventory"]["ok"] is False
    assert report["source_inventory"]["all_source_hashes_registered"] is False
    assert report["private_paths_persisted"] is False
