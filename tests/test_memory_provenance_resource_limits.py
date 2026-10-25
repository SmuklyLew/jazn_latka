"""Synthetic P1 limits fail closed before returning content equality."""
from contextlib import closing
from pathlib import Path
import sqlite3
from types import SimpleNamespace

import pytest

from latka_jazn.tools.memory_rebuild_app import p1_memory_provenance as provenance


def _pair(tmp_path: Path, *, body: str = "synthetic") -> tuple[Path, Path]:
    paths = tmp_path / "a.sqlite3", tmp_path / "b.sqlite3"
    for path in paths:
        with closing(sqlite3.connect(path)) as connection:
            connection.execute("CREATE TABLE conversations(id TEXT PRIMARY KEY, body TEXT)")
            connection.execute("INSERT INTO conversations VALUES (?,?)", ("row", body))
            connection.commit()
    return paths


def _compare(paths: tuple[Path, Path]) -> dict:
    with closing(sqlite3.connect(":memory:")) as index:
        index.execute("CREATE TABLE hashed_rows(role TEXT,table_name TEXT,key_hash TEXT,"
                      "content_hash TEXT,qty INTEGER NOT NULL,"
                      "PRIMARY KEY(role,table_name,key_hash,content_hash)) WITHOUT ROWID")
        return provenance.compare_snapshots(*paths, index=index)


def test_oversized_native_record_blocks_equality_without_source_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = _pair(tmp_path, body="x" * 4096)
    original = [path.read_bytes() for path in paths]
    monkeypatch.setattr(provenance, "MAX_ROW_BYTES", 1024)
    with pytest.raises(provenance.ComparisonBlocked, match="semantic_row_size_limit"):
        _compare(paths)
    assert [path.read_bytes() for path in paths] == original


def test_index_budget_blocks_even_small_equal_databases(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = _pair(tmp_path)
    monkeypatch.setattr(provenance, "MAX_INDEX_BYTES", 1)
    with pytest.raises(provenance.ComparisonBlocked, match="semantic_index_size_limit"):
        _compare(paths)


def test_comparison_deadline_blocks_equal_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = _pair(tmp_path)
    stamps = iter([0.0, 1000.0])
    monkeypatch.setattr(provenance, "time", SimpleNamespace(monotonic=lambda: next(stamps, 1000.0)))
    with pytest.raises(provenance.ComparisonBlocked, match="semantic_comparison_timeout"):
        _compare(paths)


def test_legitimate_bounded_comparison_still_verifies_equality(tmp_path: Path) -> None:
    result = _compare(_pair(tmp_path))
    assert result["state"] == "equal"
    assert result["fingerprint_equal"] is True
    assert result["table_diffs"] == []
