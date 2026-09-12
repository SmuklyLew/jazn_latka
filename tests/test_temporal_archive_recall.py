from __future__ import annotations

from datetime import datetime
from pathlib import Path
import sqlite3
from types import SimpleNamespace
from typing import Any

from latka_jazn.core.memory_intent_contract import parse_temporal_scope
from latka_jazn.memory.conversation_archive import (
    ConversationArchiveHit,
    ConversationArchiveStore,
)


def _build_fts(path: Path) -> None:
    with sqlite3.connect(path) as con:
        con.execute(
            """
            CREATE TABLE fts_docs(
                fts_doc_uid TEXT,
                archive_message_uid TEXT,
                archive_occurrence_uid TEXT,
                staging_uid TEXT,
                conversation_uid TEXT,
                source_uid TEXT,
                content_hash TEXT,
                role TEXT,
                title TEXT,
                create_time
            )
            """
        )
        con.execute("CREATE VIRTUAL TABLE message_fts USING fts5(content)")
        rows = [
            ("outside-before", "2024-06-15T12:00:00Z", "architecture memory"),
            *[
                (f"inside-{month:02d}", f"2025-{month:02d}-15T12:00:00Z", "architecture memory")
                for month in range(1, 13)
            ],
            ("outside-after", 1_777_281_600, "architecture memory"),
        ]
        for uid, timestamp, content in rows:
            cursor = con.execute(
                """
                INSERT INTO fts_docs VALUES(?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    uid,
                    f"message-{uid}",
                    f"occurrence-{uid}",
                    f"staging-{uid}",
                    f"conversation-{uid}",
                    "source-1",
                    f"hash-{uid}",
                    "assistant",
                    "fixture",
                    timestamp,
                ),
            )
            con.execute(
                "INSERT INTO message_fts(rowid, content) VALUES(?, ?)",
                (cursor.lastrowid, content),
            )


def _store(tmp_path: Path, monkeypatch: Any) -> ConversationArchiveStore:
    fts_path = tmp_path / "fts.sqlite3"
    _build_fts(fts_path)
    store = ConversationArchiveStore(tmp_path / "root")
    store.fts_dir = tmp_path
    monkeypatch.setattr(
        store,
        "status",
        lambda **_: SimpleNamespace(ready_for_search=True, issues=[]),
    )
    monkeypatch.setattr(
        store,
        "_manifest_rows",
        lambda *_args, **_kwargs: [
            {"family": "fts", "relative_path": fts_path.name, "shard_id": "fts-1"}
        ],
    )

    def hydrate(
        row: dict[str, Any],
        *,
        rank: float,
        terms: list[str],
        include_snippets: bool,
    ) -> ConversationArchiveHit:
        del terms, include_snippets
        uid = str(row["fts_doc_uid"])
        return ConversationArchiveHit(
            fts_doc_uid=uid,
            rank=rank,
            message_uid=str(row["archive_message_uid"]),
            occurrence_uid=str(row["archive_occurrence_uid"]),
            staging_uid=str(row["staging_uid"]),
            conversation_uid=str(row["conversation_uid"]),
            source_uid=str(row["source_uid"]),
            source_name="fixture",
            source_locator=None,
            role=str(row["role"]),
            title=str(row["title"]),
            create_time=str(row["create_time"]),
            content_hash=str(row["content_hash"]),
            memory_namespace="latka",
            privacy_scope="private",
            identity_confidence=1.0,
            review_status="accepted",
            excerpt=uid,
        )

    monkeypatch.setattr(store, "_hydrate_hit", hydrate)
    return store


def test_temporal_only_search_needs_no_literal_year_and_spreads_results(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    store = _store(tmp_path, monkeypatch)
    scope = parse_temporal_scope(
        "2025",
        now=datetime.fromisoformat("2026-08-24T12:00:00+02:00"),
    )
    assert scope is not None

    result = store.search("", temporal_scope=scope, limit=3, include_snippets=True)

    assert result.status == "ok"
    assert result.fts_query is None
    assert result.sampling_strategy == "temporal_buckets_even_spread"
    assert result.candidate_count == 12
    ids = [item["fts_doc_uid"] for item in result.hits]
    assert ids[0] == "inside-01"
    assert ids[-1] == "inside-11"
    assert len(ids) == 3


def test_lexical_search_applies_the_same_half_open_temporal_boundary(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    store = _store(tmp_path, monkeypatch)
    scope = parse_temporal_scope("2025")
    assert scope is not None

    result = store.search("architecture", temporal_scope=scope, limit=20)

    assert result.status == "ok"
    assert len(result.hits) == 12
    assert all(str(item["fts_doc_uid"]).startswith("inside-") for item in result.hits)


def test_invalid_temporal_boundary_fails_closed_before_archive_access(
    tmp_path: Path,
) -> None:
    store = ConversationArchiveStore(tmp_path)
    result = store.search(
        "",
        temporal_scope={
            "start_utc": "",
            "end_utc_exclusive": "",
            "start_epoch": 20.0,
            "end_epoch_exclusive": 10.0,
            "precision": "year",
        },
    )

    assert result.status == "invalid_temporal_scope"
    assert result.hits == []
    assert result.issues == ["invalid_temporal_scope_bounds"]
