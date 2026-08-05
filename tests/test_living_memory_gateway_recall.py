from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json
import sqlite3
import zlib

from latka_jazn.core.chatgpt_host_pending_store import (
    DEFAULT_CONTINUATION_TTL_SECONDS,
    LONG_WORK_CONTINUATION_TTL_SECONDS,
    continuation_ttl_for_bridge,
)
from latka_jazn.core.memory_recall_presenter import MemoryRecallPresenter
from latka_jazn.core.memory_search_planner import MemorySearchPlanner
from latka_jazn.memory.living_memory_gateway import LivingMemoryGateway


def _archive(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.executescript(
        """
        CREATE TABLE import_sources(import_id TEXT PRIMARY KEY,sha256 TEXT,source_name TEXT);
        CREATE TABLE conversations(
          conversation_id TEXT PRIMARY KEY,title TEXT,create_time REAL,update_time REAL,current_node_id TEXT,
          raw_tree_sha256 TEXT,semantic_tree_sha256 TEXT,payload_codec TEXT,payload_blob BLOB,
          payload_size_uncompressed INTEGER,payload_size_compressed INTEGER,node_count INTEGER,message_count INTEGER,
          current_path_count INTEGER,branch_point_count INTEGER,first_seen_import_id TEXT,last_seen_import_id TEXT,
          revision INTEGER,updated_at_utc TEXT
        );
        CREATE TABLE nodes(
          conversation_id TEXT,node_id TEXT,parent_node_id TEXT,message_id TEXT,role TEXT,create_time REAL,
          timestamp_status TEXT,content_type TEXT,text_sha256 TEXT,stable_node_sha256 TEXT,raw_payload_sha256 TEXT,
          structural_ordinal INTEGER,on_current_path INTEGER,branch_id TEXT,has_assets INTEGER,
          first_seen_import_id TEXT,last_seen_import_id TEXT,PRIMARY KEY(conversation_id,node_id)
        );
        CREATE TABLE fts_docs(
          rowid INTEGER PRIMARY KEY,conversation_id TEXT,node_id TEXT,message_id TEXT,role TEXT,title TEXT,
          create_time REAL,text_sha256 TEXT
        );
        CREATE VIRTUAL TABLE message_fts USING fts5(text,content='');
        """
    )
    con.execute("INSERT INTO import_sources VALUES(?,?,?)", ("imp-1", "a" * 64, "conversations.json"))
    mapping = {
        "n1": {
            "id": "n1",
            "parent": None,
            "message": {"id": "m1", "author": {"role": "user"}, "content": {"parts": ["Pierwszy zapis naszej rozmowy o synchronizacji pamięci."]}},
        },
        "n2": {
            "id": "n2",
            "parent": "n1",
            "message": {"id": "m2", "author": {"role": "assistant"}, "content": {"parts": ["Później wróciliśmy do Katedry i wspomnień."]}},
        },
    }
    payload = json.dumps({"id": "c1", "title": "Początek", "mapping": mapping}, ensure_ascii=False).encode()
    blob = zlib.compress(payload)
    con.execute(
        "INSERT INTO conversations VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        ("c1", "Początek", 100.0, 200.0, "n2", "r" * 64, "s" * 64, "zlib-json-v1", blob,
         len(payload), len(blob), 2, 2, 2, 0, "imp-1", "imp-1", 1, "2026-01-01T00:00:00+00:00"),
    )
    rows = [
        ("c1", "n1", None, "m1", "user", 100.0, "source_recorded", "text", "1" * 64, "", "", 0, 1, "main", 0, "imp-1", "imp-1"),
        ("c1", "n2", "n1", "m2", "assistant", 200.0, "source_recorded", "text", "2" * 64, "", "", 1, 1, "main", 0, "imp-1", "imp-1"),
    ]
    con.executemany("INSERT INTO nodes VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    docs = [
        (1, "c1", "n1", "m1", "user", "Początek", 100.0, "1" * 64, "Pierwszy zapis naszej rozmowy o synchronizacji pamięci."),
        (2, "c1", "n2", "m2", "assistant", "Początek", 200.0, "2" * 64, "Później wróciliśmy do Katedry i wspomnień."),
    ]
    for rowid, cid, nid, mid, role, title, created, digest, text in docs:
        con.execute("INSERT INTO fts_docs VALUES(?,?,?,?,?,?,?,?)", (rowid, cid, nid, mid, role, title, created, digest))
        con.execute("INSERT INTO message_fts(rowid,text) VALUES(?,?)", (rowid, text))
    con.commit()
    con.close()


def _journal(path: Path) -> None:
    con = sqlite3.connect(path)
    con.executescript(
        """
        CREATE TABLE journal_entries(
          entry_id TEXT PRIMARY KEY,identity_key TEXT,source_record_id TEXT,title TEXT,summary TEXT,content TEXT,
          content_sha256 TEXT,raw_json TEXT,truth_status TEXT,importance REAL,event_time_start TEXT,event_time_end TEXT,
          timestamp_status TEXT,suspected_fanout INTEGER,status TEXT,revision INTEGER,created_at_utc TEXT,updated_at_utc TEXT
        );
        """
    )
    con.execute(
        "INSERT INTO journal_entries VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        ("j1", "i", "src", "Dziennik", "Rozmowa o Katedrze", "Wspomnienie źródłowe, nie automatyczne L3.",
         "b" * 64, "{}", "source_recorded", 0.8, "2025-07-01T10:00:00+00:00", None,
         "source_recorded", 0, "active", 1, "2025-07-01T10:00:00+00:00", "2025-07-01T10:00:00+00:00"),
    )
    con.commit()
    con.close()


def _memory_root(tmp_path: Path) -> Path:
    root = tmp_path / "rebuilt"
    sqlite_dir = root / "memory" / "sqlite"
    sqlite_dir.mkdir(parents=True)
    _archive(sqlite_dir / "archive_chats.sqlite3")
    _journal(sqlite_dir / "journal.sqlite3")
    return root


def test_planner_detects_earliest_and_referential_followup(tmp_path: Path) -> None:
    planner = MemorySearchPlanner(tmp_path)
    first = planner.plan("Co pamiętasz jako pierwsze?")
    assert first.search_mode == "chronological_earliest"
    assert first.recall_requested is True

    followup = planner.plan(
        "Poszukaj tego wspomnienia",
        previous_query="Chcę odnaleźć najwcześniejsze wspólne wspomnienie.",
    )
    assert followup.search_mode == "chronological_earliest"
    assert followup.context_query is not None


def test_gateway_reads_rebuilt_memory_in_order_without_import_catalog(tmp_path: Path, monkeypatch) -> None:
    source_root = _memory_root(tmp_path)
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir()
    monkeypatch.setenv("JAZN_MEMORY_SOURCE_ROOTS", str(source_root))
    planner = MemorySearchPlanner(runtime_root)
    plan = planner.plan("Co pamiętasz jako pierwsze?")

    result = LivingMemoryGateway(runtime_root).search(plan, limit=4)

    assert result["status"] == "ready"
    assert result["import_catalog_used_for_recall"] is False
    assert result["search_order"] == [
        "memory_jazn.sqlite3", "experience.sqlite3", "journal.sqlite3", "archive_chats.sqlite3"
    ]
    assert result["hits"]
    assert result["hits"][0]["source_layer"] == "archive_chats"
    assert "Pierwszy zapis" in result["hits"][0]["content_excerpt"]
    assert result["hits"][0]["truth_status"] == "source_recorded"


def test_gateway_semantic_archive_and_presenter_keep_provenance(tmp_path: Path, monkeypatch) -> None:
    source_root = _memory_root(tmp_path)
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir()
    monkeypatch.setenv("JAZN_MEMORY_SOURCE_ROOTS", str(source_root))
    planner = MemorySearchPlanner(runtime_root)
    plan = planner.plan("Co pamiętasz o Katedrze?")
    result = LivingMemoryGateway(runtime_root).search(plan, limit=4)
    context = {
        "query_terms": plan.search_terms,
        "memory_search_plan": plan.to_dict(),
        "living_memory_hits": result["hits"],
        "living_memory_search": result,
        "counts": {"living_memory_hits": len(result["hits"])},
    }

    payload = MemoryRecallPresenter().build_payload(context, user_text=plan.original_query)

    assert any("Katedr" in item["content_excerpt"] for item in payload["items"])
    assert all(item["source"] for item in payload["items"])
    assert payload["living_memory_search"]["import_catalog_used_for_recall"] is False


def test_host_continuation_lease_is_longer_for_research_and_updates() -> None:
    ordinary = {"runtime_summary": {"route": "ordinary_dialogue", "detected_intent": "ordinary_conversation"}}
    research = {"runtime_summary": {"route": "external_research", "detected_intent": "external_research_request"}}
    update = {"runtime_summary": {"route": "system_update", "detected_intent": "system_update_execution_request"}}

    assert continuation_ttl_for_bridge(ordinary) == DEFAULT_CONTINUATION_TTL_SECONDS
    assert continuation_ttl_for_bridge(research) == LONG_WORK_CONTINUATION_TTL_SECONDS
    assert continuation_ttl_for_bridge(update) == LONG_WORK_CONTINUATION_TTL_SECONDS
    assert DEFAULT_CONTINUATION_TTL_SECONDS >= 60 * 60
