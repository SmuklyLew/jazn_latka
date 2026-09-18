from __future__ import annotations

import sqlite3

import pytest

from latka_jazn.tools.memory_rebuild_app.read_only_validation import _fts_smoke_queries


def _database(source: str, indexed: str) -> sqlite3.Connection:
    con = sqlite3.connect(":memory:")
    con.execute("CREATE TABLE memory_l0_records(content TEXT, is_current_revision INTEGER)")
    con.execute("CREATE VIRTUAL TABLE memory_l0_fts USING fts5(content, tokenize='unicode61 remove_diacritics 2')")
    con.execute("INSERT INTO memory_l0_records VALUES(?,1)", (source,))
    con.execute("INSERT INTO memory_l0_fts VALUES(?)", (indexed,))
    con.commit()
    con.execute("PRAGMA query_only=ON")
    return con


@pytest.mark.parametrize("source", [
    '{"context":"Replacement text"}',
    "alpha-beta evidence",
    "alpha_beta evidence",
    "x-y",
    "zażółć gęślą",
])
def test_source_punctuation_uses_real_fts_tokens(source: str) -> None:
    """A healthy source index must match tokens without concatenating punctuation boundaries."""
    con = _database(source, source)
    try:
        before = con.total_changes
        report = _fts_smoke_queries(con, "memory_l0_fts")
        assert report["ok"] is True
        assert report["matches"] == 1
        assert con.total_changes == before
    finally:
        con.close()


def test_source_probe_detects_index_without_source_terms() -> None:
    """A populated index missing the source evidence must still fail the source probe."""
    con = _database('{"context":"Replacement text"}', "unrelated words")
    try:
        report = _fts_smoke_queries(con, "memory_l0_fts")
        assert report["ok"] is False
        assert report["status"] == "no_match"
        assert report["matches"] == 0
    finally:
        con.close()
