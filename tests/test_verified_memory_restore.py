from __future__ import annotations

from pathlib import Path
import hashlib
import json
import sqlite3
import zlib

import pytest

from latka_jazn.memory.conversation_archive import ConversationArchiveStore
from latka_jazn.tools.verified_memory_restore import (
    L2_DRAFT_SCHEMA,
    RuntimeArchiveConverter,
    VerifiedMemoryRestoreError,
    seal_l2_review,
    validate_test04_databases,
    validate_test04_summary,
)


def _conversation_payload() -> dict:
    return {
        "id": "conv-1",
        "title": "Pamięć warstwowa",
        "create_time": 1_753_000_000.0,
        "update_time": 1_753_000_100.0,
        "current_node": "node-assistant",
        "mapping": {
            "node-user": {
                "id": "node-user",
                "parent": None,
                "children": ["node-assistant"],
                "message": {
                    "id": "msg-user",
                    "author": {"role": "user"},
                    "create_time": 1_753_000_000.0,
                    "content": {
                        "content_type": "text",
                        "parts": ["Pamięć ma być warstwowa i prawdziwa."],
                    },
                },
            },
            "node-assistant": {
                "id": "node-assistant",
                "parent": "node-user",
                "children": [],
                "message": {
                    "id": "msg-assistant",
                    "author": {"role": "assistant"},
                    "create_time": 1_753_000_100.0,
                    "content": {
                        "content_type": "text",
                        "parts": ["Najpierw źródło, potem jawna promocja."],
                    },
                },
            },
        },
    }


def _create_test04_root(root: Path) -> Path:
    sqlite_root = root / "memory/sqlite"
    sqlite_root.mkdir(parents=True)
    archive = sqlite_root / "archive_chats.sqlite3"
    payload = json.dumps(
        _conversation_payload(),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    with sqlite3.connect(archive) as con:
        con.executescript(
            """
            CREATE TABLE import_sources(
              import_id TEXT PRIMARY KEY,sha256 TEXT,source_name TEXT,source_path TEXT,
              size_bytes INTEGER,status TEXT,started_at_utc TEXT,completed_at_utc TEXT,
              conversation_count INTEGER,node_count INTEGER,message_count INTEGER,
              report_json TEXT
            );
            CREATE TABLE conversations(
              conversation_id TEXT PRIMARY KEY,title TEXT,create_time REAL,update_time REAL,
              current_node_id TEXT,raw_tree_sha256 TEXT,semantic_tree_sha256 TEXT,
              payload_codec TEXT,payload_blob BLOB,payload_size_uncompressed INTEGER,
              payload_size_compressed INTEGER,node_count INTEGER,message_count INTEGER,
              current_path_count INTEGER,branch_point_count INTEGER,
              first_seen_import_id TEXT,last_seen_import_id TEXT,revision INTEGER,
              updated_at_utc TEXT
            );
            CREATE TABLE nodes(
              conversation_id TEXT,node_id TEXT,parent_node_id TEXT,message_id TEXT,role TEXT,
              create_time REAL,timestamp_status TEXT,content_type TEXT,text_sha256 TEXT,
              stable_node_sha256 TEXT,raw_payload_sha256 TEXT,structural_ordinal INTEGER,
              on_current_path INTEGER,branch_id TEXT,has_assets INTEGER,
              first_seen_import_id TEXT,last_seen_import_id TEXT,
              PRIMARY KEY(conversation_id,node_id)
            );
            CREATE TABLE conversation_occurrences(
              conversation_id TEXT,import_id TEXT,relation_to_active TEXT,
              raw_tree_sha256 TEXT,semantic_tree_sha256 TEXT,node_count INTEGER,
              message_count INTEGER,observed_at_utc TEXT,
              PRIMARY KEY(conversation_id,import_id)
            );
            """
        )
        con.execute(
            "INSERT INTO import_sources VALUES(?,?,?,?,?,'completed',?,?,?,?,?,?)",
            (
                "src-1",
                "a" * 64,
                "export.zip",
                "D:/PRIVATE/export.zip",
                123,
                "2026-07-30T00:00:00+00:00",
                "2026-07-30T00:01:00+00:00",
                1,
                2,
                2,
                "{}",
            ),
        )
        compressed = zlib.compress(payload)
        con.execute(
            """INSERT INTO conversations VALUES(
               ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                "conv-1",
                "Pamięć warstwowa",
                1_753_000_000.0,
                1_753_000_100.0,
                "node-assistant",
                "b" * 64,
                "c" * 64,
                "zlib-json-v1",
                compressed,
                len(payload),
                len(compressed),
                2,
                2,
                2,
                0,
                "src-1",
                "src-1",
                1,
                "2026-07-30T00:01:00+00:00",
            ),
        )
        for ordinal, (node_id, parent, message_id, role, timestamp) in enumerate(
            (
                ("node-user", None, "msg-user", "user", 1_753_000_000.0),
                (
                    "node-assistant",
                    "node-user",
                    "msg-assistant",
                    "assistant",
                    1_753_000_100.0,
                ),
            ),
            start=1,
        ):
            con.execute(
                """INSERT INTO nodes(
                   conversation_id,node_id,parent_node_id,message_id,role,
                   create_time,timestamp_status,content_type,text_sha256,
                   stable_node_sha256,raw_payload_sha256,structural_ordinal,
                   on_current_path,branch_id,has_assets,first_seen_import_id,
                   last_seen_import_id
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    "conv-1",
                    node_id,
                    parent,
                    message_id,
                    role,
                    timestamp,
                    "exact",
                    "text",
                    hashlib.sha256(message_id.encode()).hexdigest(),
                    hashlib.sha256(node_id.encode()).hexdigest(),
                    None,
                    ordinal,
                    1,
                    "main",
                    0,
                    "src-1",
                    "src-1",
                ),
            )
        con.execute(
            "INSERT INTO conversation_occurrences VALUES(?,?,?,?,?,?,?,?)",
            (
                "conv-1",
                "src-1",
                "new",
                "b" * 64,
                "c" * 64,
                2,
                2,
                "2026-07-30T00:01:00+00:00",
            ),
        )

    journal = sqlite_root / "journal.sqlite3"
    with sqlite3.connect(journal) as con:
        con.execute(
            """CREATE TABLE journal_entries(
               entry_id TEXT PRIMARY KEY,source_record_id TEXT,title TEXT,summary TEXT,
               content TEXT,raw_json TEXT,truth_status TEXT,importance REAL,
               event_time_start TEXT,event_time_end TEXT,timestamp_status TEXT,
               revision INTEGER,status TEXT,updated_at_utc TEXT)"""
        )
        raw = {
            "id": "j1",
            "timestamp": "2026-07-30T00:02:00+00:00",
            "typ": "ustalenie",
            "treść": "Nie promować automatycznie do L3.",
        }
        con.execute(
            "INSERT INTO journal_entries VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "entry-1",
                "j1",
                "Granica L3",
                "",
                raw["treść"],
                json.dumps(raw, ensure_ascii=False),
                "user_confirmed",
                0.9,
                raw["timestamp"],
                None,
                "exact",
                1,
                "active",
                raw["timestamp"],
            ),
        )

    for filename in ("memory_jazn.sqlite3", "experience.sqlite3", "import_catalog.sqlite3"):
        with sqlite3.connect(sqlite_root / filename) as con:
            con.execute("CREATE TABLE smoke(id INTEGER PRIMARY KEY)")
    return root


def _summary(path: Path, *, recall: str = "passed") -> Path:
    payload = {
        "schema_version": "jazn_memory_sqlite_test04/v1",
        "final": {
            "structural_integrity": "passed",
            "source_completeness": "passed",
            "same_target_idempotence": "passed",
            "fresh_rebuild_reproducibility": "passed",
            "test03_reconciliation": "passed",
            "recall": recall,
            "html_import_dry_run": "not_applicable",
            "multi_turn_review": "passed",
            "system_activation_ready": False,
        },
        "error_count": 0,
        "system_activation_performed": False,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_converter_builds_searchable_current_archive(tmp_path: Path) -> None:
    test04_root = _create_test04_root(tmp_path / "test04")
    validate_test04_databases(test04_root)
    output = tmp_path / "runtime"
    result = RuntimeArchiveConverter(test04_root, output).build()
    assert result["ok"] is True
    status = ConversationArchiveStore(output).status(health_mode="deep")
    assert status.ready_for_search is True
    search = ConversationArchiveStore(output).search(
        "warstwowa prawdziwa",
        limit=5,
        include_snippets=True,
    )
    assert search.status == "ok"
    assert search.hits
    assert "warstwowa" in search.hits[0]["excerpt"].lower()
    journal = json.loads(
        (output / "memory/raw/dziennik.json").read_text(encoding="utf-8")
    )
    assert len(journal["entries"]) == 1


def test_test04_summary_is_fail_closed(tmp_path: Path) -> None:
    valid = _summary(tmp_path / "summary.json")
    assert validate_test04_summary(valid)["ok"] is True
    invalid = _summary(tmp_path / "invalid.json", recall="not_run")
    with pytest.raises(VerifiedMemoryRestoreError, match="recall"):
        validate_test04_summary(invalid)


def test_l2_seal_requires_decision_for_every_candidate(tmp_path: Path) -> None:
    draft = {
        "schema_version": L2_DRAFT_SCHEMA,
        "candidates": [
            {
                "item_id": "candidate-1",
                "content_excerpt": "Źródłowa treść.",
                "content_excerpt_sha256": hashlib.sha256(
                    "Źródłowa treść.".encode("utf-8")
                ).hexdigest(),
                "decision": "pending_review",
                "review_note": "",
            }
        ],
    }
    draft_path = tmp_path / "draft.json"
    draft_path.write_text(json.dumps(draft, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(VerifiedMemoryRestoreError, match="niekompletny"):
        seal_l2_review(
            draft_path,
            reviewed_by="Krzysztof",
            output_path=tmp_path / "sealed.json",
        )
    draft["candidates"][0]["decision"] = "approved"
    draft_path.write_text(json.dumps(draft, ensure_ascii=False), encoding="utf-8")
    sealed = seal_l2_review(
        draft_path,
        reviewed_by="Krzysztof",
        output_path=tmp_path / "sealed.json",
    )
    assert sealed["approved_count"] == 1
    assert sealed["manifest_sha256"]
