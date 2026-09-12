from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
import json
import sqlite3
import zlib

import pytest

from latka_jazn.core.memory_intent_contract import parse_temporal_scope
from latka_jazn.core.memory_search_planner import MemorySearchPlanner
from latka_jazn.memory.living_memory_gateway import LivingMemoryGateway, LivingMemoryHit


NOW = datetime(2026, 8, 24, 12, 0, tzinfo=timezone.utc)
INSTANT_2024 = "2024-07-10T10:00:00+00:00"
INSTANT_2025 = "2025-07-10T10:00:00+00:00"
INSTANT_2026 = "2026-07-10T10:00:00+00:00"


def _epoch(value: str) -> float:
    return datetime.fromisoformat(value).timestamp()


def _memory_database(path: Path) -> None:
    with sqlite3.connect(path) as con:
        con.executescript(
            """
            CREATE TABLE memory_records(
              memory_id TEXT PRIMARY KEY,tier TEXT,kind TEXT,content TEXT,domain TEXT,
              truth_status TEXT,confidence REAL,importance REAL,created_at_utc TEXT,
              updated_at_utc TEXT,active INTEGER
            );
            """
        )
        rows = [
            ("memory-out", INSTANT_2024),
            ("memory-in", INSTANT_2025),
            ("memory-future", INSTANT_2026),
        ]
        con.executemany(
            "INSERT INTO memory_records VALUES(?,?,?,?,?,?,?,?,?,?,1)",
            [
                (record_id, "long_term", "scene", "Rozmowa przy Katedrze", "shared", "source_recorded", 0.9, 0.8, instant, instant)
                for record_id, instant in rows
            ],
        )


def _experience_database(path: Path) -> None:
    with sqlite3.connect(path) as con:
        con.executescript(
            """
            CREATE TABLE experiences(
              experience_id TEXT PRIMARY KEY,title TEXT,summary TEXT,truth_status TEXT,
              confidence REAL,importance REAL,status TEXT,created_at_utc TEXT,updated_at_utc TEXT
            );
            """
        )
        rows = [
            ("experience-out", INSTANT_2024),
            ("experience-in", INSTANT_2025),
            ("experience-future", INSTANT_2026),
        ]
        con.executemany(
            "INSERT INTO experiences VALUES(?,?,?,?,?,?,?,?,?)",
            [
                (record_id, "Przy Katedrze", "Źródłowe doświadczenie rozmowy", "source_recorded", 0.85, 0.75, "approved", instant, instant)
                for record_id, instant in rows
            ],
        )


def _journal_database(path: Path) -> None:
    with sqlite3.connect(path) as con:
        con.executescript(
            """
            CREATE TABLE journal_entries(
              entry_id TEXT PRIMARY KEY,title TEXT,summary TEXT,content TEXT,truth_status TEXT,
              importance REAL,event_time_start TEXT,created_at_utc TEXT,status TEXT
            );
            """
        )
        rows = [
            ("journal-out", INSTANT_2024),
            ("journal-in", INSTANT_2025),
            ("journal-future", INSTANT_2026),
        ]
        con.executemany(
            "INSERT INTO journal_entries VALUES(?,?,?,?,?,?,?,?,?)",
            [
                (record_id, "Przy Katedrze", "Dziennik rozmowy", "Źródłowy wpis", "source_recorded", 0.7, instant, instant, "active")
                for record_id, instant in rows
            ],
        )


def _archive_database(path: Path) -> None:
    with sqlite3.connect(path) as con:
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
        con.execute(
            "INSERT INTO import_sources VALUES(?,?,?)",
            ("synthetic-import", "a" * 64, "synthetic-conversations.json"),
        )
        node_specs = [
            ("archive-out", None, "m-out", INSTANT_2024),
            ("archive-in", "archive-out", "m-in", INSTANT_2025),
            ("archive-future", "archive-in", "m-future", INSTANT_2026),
        ]
        mapping: dict[str, Any] = {}
        for node_id, parent_id, message_id, instant in node_specs:
            mapping[node_id] = {
                "id": node_id,
                "parent": parent_id,
                "message": {
                    "id": message_id,
                    "author": {"role": "assistant"},
                    "create_time": _epoch(instant),
                    "content": {"parts": [f"Rozmowa przy Katedrze {node_id}."]},
                },
            }
        payload = json.dumps(
            {"id": "synthetic-conversation", "title": "Syntetyczna rozmowa", "mapping": mapping},
            ensure_ascii=False,
        ).encode("utf-8")
        blob = zlib.compress(payload)
        con.execute(
            "INSERT INTO conversations VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "synthetic-conversation", "Syntetyczna rozmowa", _epoch(INSTANT_2024), _epoch(INSTANT_2026),
                "archive-future", "r" * 64, "s" * 64, "zlib-json-v1", blob, len(payload), len(blob),
                3, 3, 3, 0, "synthetic-import", "synthetic-import", 1, INSTANT_2026,
            ),
        )
        for ordinal, (node_id, parent_id, message_id, instant) in enumerate(node_specs):
            con.execute(
                "INSERT INTO nodes VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    "synthetic-conversation", node_id, parent_id, message_id, "assistant", _epoch(instant),
                    "source_recorded", "text", str(ordinal + 1) * 64, "stable", "raw", ordinal, 1,
                    "main", 0, "synthetic-import", "synthetic-import",
                ),
            )
            con.execute(
                "INSERT INTO fts_docs VALUES(?,?,?,?,?,?,?,?)",
                (
                    ordinal + 1, "synthetic-conversation", node_id, message_id, "assistant",
                    "Syntetyczna rozmowa", _epoch(instant), str(ordinal + 1) * 64,
                ),
            )
            con.execute(
                "INSERT INTO message_fts(rowid,text) VALUES(?,?)",
                (ordinal + 1, f"Rozmowa przy Katedrze {node_id}."),
            )


def _legacy_memory_root(tmp_path: Path) -> Path:
    source_root = tmp_path / "synthetic-memory"
    sqlite_dir = source_root / "memory" / "sqlite"
    sqlite_dir.mkdir(parents=True)
    _memory_database(sqlite_dir / "memory_jazn.sqlite3")
    _experience_database(sqlite_dir / "experience.sqlite3")
    _journal_database(sqlite_dir / "journal.sqlite3")
    _archive_database(sqlite_dir / "archive_chats.sqlite3")
    return source_root


@pytest.mark.parametrize(
    "prompt,expected_mode",
    [
        ("Powspominaj 2025 rok.", "temporal_period"),
        ("Co pamiętasz o Katedrze z 2025 roku?", "temporal_semantic_query"),
    ],
)
def test_temporal_scope_filters_all_living_layers_before_selection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    prompt: str,
    expected_mode: str,
) -> None:
    source_root = _legacy_memory_root(tmp_path)
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir()
    monkeypatch.setenv("JAZN_MEMORY_SOURCE_ROOTS", str(source_root))
    plan = MemorySearchPlanner(runtime_root).plan(prompt, now=NOW)

    result = LivingMemoryGateway(runtime_root).search(plan, limit=12)

    assert plan.search_mode == expected_mode
    if expected_mode == "temporal_period":
        assert plan.search_terms == []
        assert result["query"] == ""
    assert result["temporal_filter"]["status"] == "applied"
    ids_by_layer = {
        str(hit["source_layer"]): str(hit["record_id"])
        for hit in result["hits"]
    }
    assert ids_by_layer == {
        "memory_jazn": "memory-in",
        "experience": "experience-in",
        "journal": "journal-in",
        "archive_chats": "archive-in",
    }
    assert all("-out" not in record_id and "-future" not in record_id for record_id in ids_by_layer.values())


def test_post_filter_removes_out_of_scope_candidate_before_graph_ranking(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir()
    database = tmp_path / "synthetic.sqlite3"
    database.touch()
    gateway = LivingMemoryGateway(runtime_root)
    scope = parse_temporal_scope("2025 rok", now=NOW)
    assert scope is not None
    plan = SimpleNamespace(
        search_mode="temporal_period",
        search_terms=[],
        focus_terms=[],
        temporal_scope=scope.to_dict(),
    )
    monkeypatch.setattr(
        gateway,
        "discover",
        lambda: [{
            "recall_ready": True,
            "memory_search_ready": False,
            "legacy_search_ready": True,
            "database_paths": {"memory_jazn": str(database)},
        }],
    )

    def fake_memory_search(*args: Any, **kwargs: Any) -> list[LivingMemoryHit]:
        return [
            LivingMemoryHit("memory_jazn", str(database), "memory_records:out", "out", "poza", INSTANT_2024, "source_recorded", 0.8, 0.8, 0.9),
            LivingMemoryHit("memory_jazn", str(database), "memory_records:missing", "missing", "bez czasu", None, "source_recorded", 0.8, 0.8, 0.85),
            LivingMemoryHit("memory_jazn", str(database), "memory_records:in", "in", "wewnątrz", INSTANT_2025, "source_recorded", 0.8, 0.8, 0.8),
        ]

    monkeypatch.setattr(gateway, "_search_memory", fake_memory_search)

    class RecordingGraph:
        observed: list[LivingMemoryHit] = []

        def select(self, hits: Any, **kwargs: Any) -> SimpleNamespace:
            self.observed = list(hits)
            return SimpleNamespace(selected=tuple(self.observed), telemetry={"status": "recorded"})

    recorder = RecordingGraph()
    cast(Any, gateway).graph_retrieval = recorder

    result = gateway.search(plan, limit=6)

    assert [hit.record_id for hit in recorder.observed] == ["in"]
    assert [hit["record_id"] for hit in result["hits"]] == ["in"]
    assert result["counts"]["temporal_filtered_out"] == 2


def test_invalid_temporal_scope_fails_closed_before_any_layer_or_graph_search(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir()
    database = tmp_path / "synthetic.sqlite3"
    database.touch()
    gateway = LivingMemoryGateway(runtime_root)
    monkeypatch.setattr(
        gateway,
        "discover",
        lambda: [{
            "recall_ready": True,
            "memory_search_ready": False,
            "legacy_search_ready": True,
            "database_paths": {"memory_jazn": str(database)},
        }],
    )

    def forbidden_search(*args: Any, **kwargs: Any) -> list[LivingMemoryHit]:
        raise AssertionError("invalid temporal scope must block every memory layer")

    monkeypatch.setattr(gateway, "_search_memory", forbidden_search)

    class ForbiddenGraph:
        def select(self, *args: Any, **kwargs: Any) -> Any:
            raise AssertionError("invalid temporal scope must not reach graph ranking")

    cast(Any, gateway).graph_retrieval = ForbiddenGraph()
    plan = SimpleNamespace(
        search_mode="temporal_period",
        search_terms=[],
        focus_terms=[],
        temporal_scope={
            "start_epoch": _epoch(INSTANT_2026),
            "end_epoch_exclusive": _epoch(INSTANT_2025),
            "precision": "year",
        },
    )

    result = gateway.search(plan, limit=6)

    assert result["status"] == "invalid_temporal_scope"
    assert result["hits"] == []
    assert result["temporal_filter"]["status"] == "invalid_fail_closed"
    assert result["graph_retrieval"]["status"] == "bypassed_invalid_temporal_scope"
    assert result["issues"] == ["temporal_scope:invalid_bounds"]
