from __future__ import annotations

from pathlib import Path
import sqlite3

from latka_jazn.memory.memory_tier_reader import (
    probe_memory_tier_database_readonly,
    search_memory_tier_database_readonly,
)


def _build_database(path: Path) -> None:
    con = sqlite3.connect(path)
    try:
        con.executescript(
            """
            PRAGMA foreign_keys=ON;
            CREATE TABLE memory_store_meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
            INSERT INTO memory_store_meta(key,value) VALUES('schema_version','memory_store/v3.0');
            CREATE TABLE memory_records(
                memory_id TEXT PRIMARY KEY,
                tier TEXT NOT NULL,
                kind TEXT NOT NULL,
                content TEXT NOT NULL,
                domain TEXT NOT NULL,
                mode TEXT NOT NULL,
                truth_status TEXT NOT NULL,
                confidence REAL NOT NULL,
                importance REAL NOT NULL,
                created_at_utc TEXT NOT NULL,
                updated_at_utc TEXT NOT NULL,
                tags_json TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1
            );
            CREATE TABLE memory_evidence(
                evidence_key TEXT PRIMARY KEY,
                memory_id TEXT NOT NULL,
                source_type TEXT NOT NULL,
                source_id TEXT NOT NULL,
                FOREIGN KEY(memory_id) REFERENCES memory_records(memory_id)
            );
            CREATE VIRTUAL TABLE memory_records_fts USING fts5(
                content,
                kind,
                domain,
                content='memory_records',
                content_rowid='rowid'
            );
            CREATE TRIGGER memory_records_ai AFTER INSERT ON memory_records BEGIN
                INSERT INTO memory_records_fts(rowid,content,kind,domain)
                VALUES(new.rowid,new.content,new.kind,new.domain);
            END;
            CREATE TRIGGER memory_records_ad AFTER DELETE ON memory_records BEGIN
                INSERT INTO memory_records_fts(memory_records_fts,rowid,content,kind,domain)
                VALUES('delete',old.rowid,old.content,old.kind,old.domain);
            END;
            CREATE TRIGGER memory_records_au AFTER UPDATE ON memory_records BEGIN
                INSERT INTO memory_records_fts(memory_records_fts,rowid,content,kind,domain)
                VALUES('delete',old.rowid,old.content,old.kind,old.domain);
                INSERT INTO memory_records_fts(rowid,content,kind,domain)
                VALUES(new.rowid,new.content,new.kind,new.domain);
            END;
            """
        )
        rows = [
            (
                "m1", "L2", "episodic", "Wspomnienie o czerwonej włóczce i tarasie.",
                "conversation", "reviewed", "source_recorded", 0.95, 0.8,
                "2026-08-20T10:00:00+00:00", "2026-08-20T10:00:00+00:00", "[]", 1,
            ),
            (
                "m2", "L1", "operational", "Notatka o ustawieniach terminala i logach.",
                "runtime", "automatic", "source_recorded", 0.8, 0.5,
                "2026-08-21T10:00:00+00:00", "2026-08-21T10:00:00+00:00", "[]", 1,
            ),
        ]
        con.executemany(
            """INSERT INTO memory_records(
                   memory_id,tier,kind,content,domain,mode,truth_status,confidence,importance,
                   created_at_utc,updated_at_utc,tags_json,active
               ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            rows,
        )
        con.execute(
            "INSERT INTO memory_evidence(evidence_key,memory_id,source_type,source_id) VALUES(?,?,?,?)",
            ("ev1", "m1", "conversation", "turn-1"),
        )
        con.commit()
    finally:
        con.close()


def test_probe_reports_fts5_and_direct_rank_search(tmp_path: Path) -> None:
    database = tmp_path / "memory_jazn.sqlite3"
    _build_database(database)

    probe = probe_memory_tier_database_readonly(database)
    assert probe["memory_search_ready"] is True
    assert probe["fts5_available"] is True

    results = search_memory_tier_database_readonly(database, "czerwona włóczka", limit=4)

    assert [row["memory_id"] for row in results] == ["m1"]
    assert results[0]["search_index"] == "memory_records_fts:rank"
    assert results[0]["evidence_sources"] == [
        {"source_type": "conversation", "source_id": "turn-1"}
    ]
