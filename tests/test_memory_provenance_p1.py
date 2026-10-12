from __future__ import annotations

from contextlib import closing
from pathlib import Path
import sqlite3
import pytest

from latka_jazn.tools.memory_rebuild_app.models import RebuildProject
from latka_jazn.tools.memory_rebuild_app.p1_memory_provenance import (
    ComparisonBlocked, SCHEMA, compare_memory_provenance, compare_snapshots,
)


def make_db(path: Path, records: tuple[tuple[str, str], ...]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path)) as conn:
        conn.execute("CREATE TABLE conversations(id TEXT PRIMARY KEY, body TEXT)")
        conn.executemany("INSERT INTO conversations VALUES (?,?)", records)
        conn.commit()


def compare_pair(tmp_path: Path, a: tuple[tuple[str, str], ...], b: tuple[tuple[str, str], ...]):
    p, q = tmp_path / "a.sqlite3", tmp_path / "b.sqlite3"
    make_db(p, a)
    make_db(q, b)
    with closing(sqlite3.connect(":memory:")) as index:
        index.execute(
            "CREATE TABLE hashed_rows(role TEXT,table_name TEXT,key_hash TEXT,"
            "content_hash TEXT,qty INTEGER NOT NULL,"
            "PRIMARY KEY(role,table_name,key_hash,content_hash)) WITHOUT ROWID"
        )
        return compare_snapshots(p, q, index=index)


def test_equal_rows_independent_of_insertion_order(tmp_path: Path) -> None:
    data = (("1", "synthetic A"), ("2", "synthetic B"))
    result = compare_pair(tmp_path, data, tuple(reversed(data)))
    assert result["state"] == "equal"
    assert result["fingerprint_equal"] is True
    assert result["table_diffs"] == []
    assert "synthetic" not in str(result)


def test_modified_key_payload_and_addition(tmp_path: Path) -> None:
    result = compare_pair(tmp_path, (("1", "before"),), (("1", "after"), ("2", "new")))
    assert result["state"] == "different"
    assert result["table_diffs"] == [
        {"table": "conversations", "added": 1, "removed": 0, "changed": 1}
    ]
    assert "before" not in str(result)
    assert "after" not in str(result)


def test_removed_key(tmp_path: Path) -> None:
    result = compare_pair(tmp_path, (("1", "old"), ("2", "keep")), (("2", "keep"),))
    assert result["table_diffs"][0]["removed"] == 1


def test_table_schema_difference_blocks_equality(tmp_path: Path) -> None:
    first, second = tmp_path / "a.sqlite3", tmp_path / "b.sqlite3"
    make_db(first, (("1", "x"),))
    second.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(second)) as con:
        con.execute("CREATE TABLE conversations(id TEXT PRIMARY KEY, renamed TEXT)")
        con.commit()
    with closing(sqlite3.connect(":memory:")) as index:
        index.execute(
            "CREATE TABLE hashed_rows(role TEXT,table_name TEXT,key_hash TEXT,"
            "content_hash TEXT,qty INTEGER NOT NULL,"
            "PRIMARY KEY(role,table_name,key_hash,content_hash)) WITHOUT ROWID"
        )
        result = compare_snapshots(first, second, index=index)
    assert result["state"] == "incompatible"


def test_record_limit_is_fail_closed(tmp_path: Path) -> None:
    first, second = tmp_path / "a.sqlite3", tmp_path / "b.sqlite3"
    make_db(first, (("1", "x"), ("2", "y")))
    make_db(second, (("1", "x"),))
    with closing(sqlite3.connect(":memory:")) as index:
        index.execute(
            "CREATE TABLE hashed_rows(role TEXT,table_name TEXT,key_hash TEXT,"
            "content_hash TEXT,qty INTEGER NOT NULL,"
            "PRIMARY KEY(role,table_name,key_hash,content_hash)) WITHOUT ROWID"
        )
        with pytest.raises(ComparisonBlocked, match="semantic_row_limit"):
            compare_snapshots(first, second, index=index, max_rows=1)


def test_foreign_db_is_not_promoted_to_comparable_native(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    system = tmp_path / "system"
    system.mkdir()
    monkeypatch.setenv("JAZN_MEMORY_ROOT", str(tmp_path / "private"))
    project = RebuildProject.create("synthetic", tmp_path / "stage")
    db = tmp_path / "stage/memory/sqlite/memory_jazn.sqlite3"
    make_db(db, (("1", "private text"),))
    before = db.read_bytes()
    report = compare_memory_provenance(project, system_root=system)
    assert report["schema"] == SCHEMA
    assert report["issue"] == "target_native_unverified"
    assert report["activation_ready"] is False
    assert report["publishing_authorized"] is False
    assert report["private_content_returned"] is False
    assert db.read_bytes() == before
    assert str(tmp_path) not in str(report)
