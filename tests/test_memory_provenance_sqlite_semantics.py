"""P1 logical differences preserve SQLite keys, types and multiplicity."""
from contextlib import closing
from pathlib import Path
import sqlite3

import pytest

from latka_jazn.tools.memory_rebuild_app.p1_memory_provenance import compare_snapshots


def _compare(tmp_path: Path, schema: str, left: list[tuple], right: list[tuple]) -> dict:
    paths = [tmp_path / "left.sqlite3", tmp_path / "right.sqlite3"]
    for path, rows in zip(paths, (left, right)):
        with closing(sqlite3.connect(path)) as connection:
            connection.execute(schema)
            placeholders = ",".join("?" for _ in rows[0])
            connection.executemany(f"INSERT INTO conversations VALUES ({placeholders})", rows)
            connection.commit()
    with closing(sqlite3.connect(":memory:")) as index:
        index.execute("CREATE TABLE hashed_rows(role TEXT,table_name TEXT,key_hash TEXT,"
                      "content_hash TEXT,qty INTEGER NOT NULL,"
                      "PRIMARY KEY(role,table_name,key_hash,content_hash)) WITHOUT ROWID")
        return compare_snapshots(*paths, index=index)


def test_composite_primary_key_identifies_one_modified_row(tmp_path: Path) -> None:
    result = _compare(tmp_path,
        "CREATE TABLE conversations(a TEXT,b INTEGER,body TEXT,PRIMARY KEY(a,b))",
        [("synthetic", 1, "same"), ("synthetic", 2, "before")],
        [("synthetic", 2, "after"), ("synthetic", 1, "same")])
    assert result["state"] == "different"
    assert result["table_diffs"] == [{"table": "conversations", "added": 0, "removed": 0, "changed": 1}]


def test_no_primary_key_retains_duplicate_multiplicity(tmp_path: Path) -> None:
    row = (None, b"\x00\xff", "Zażółć")
    result = _compare(tmp_path, "CREATE TABLE conversations(a,b,c)", [row, row], [row])
    assert result["state"] == "different"
    assert result["table_diffs"] == [{"table": "conversations", "added": 0, "removed": 0, "changed": 1}]
    assert "Zażółć" not in str(result)


@pytest.mark.parametrize("before,after", [(None, ""), (1, "1"), (1, 1.0), (b"abc", "abc")])
def test_sqlite_storage_types_are_distinct(tmp_path: Path, before: object, after: object) -> None:
    result = _compare(tmp_path, "CREATE TABLE conversations(id TEXT PRIMARY KEY,body)",
                      [("row", before)], [("row", after)])
    assert result["state"] == "different"
    assert result["table_diffs"][0]["changed"] == 1


def test_volatile_timestamp_does_not_change_semantic_fingerprint(tmp_path: Path) -> None:
    result = _compare(tmp_path,
        "CREATE TABLE conversations(id TEXT PRIMARY KEY,body TEXT,updated_at_utc TEXT)",
        [("row", "synthetic", "2020-01-01")], [("row", "synthetic", "2026-01-01")])
    assert result["state"] == "equal"
    assert result["fingerprint_equal"] is True


def test_volatile_named_column_remains_significant_when_it_is_the_key(tmp_path: Path) -> None:
    result = _compare(tmp_path,
        "CREATE TABLE conversations(updated_at_utc TEXT PRIMARY KEY,body TEXT)",
        [("2020-01-01", "synthetic")], [("2026-01-01", "synthetic")])
    assert result["state"] == "different"
    assert result["table_diffs"] == [{"table": "conversations", "added": 1, "removed": 1, "changed": 0}]
