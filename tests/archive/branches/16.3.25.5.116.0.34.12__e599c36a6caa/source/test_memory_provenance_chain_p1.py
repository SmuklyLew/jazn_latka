"""Frozen synthetic SQLite pins: no PRIVATE MEMORY, no activation."""
from __future__ import annotations

from contextlib import closing
import hashlib
from pathlib import Path
import shutil
import sqlite3

import pytest

from latka_jazn.tools.memory_rebuild_app.p1_provenance_chain import (
    PinnedMemoryArtifact, verify_provenance_chain,
)
from latka_jazn.tools.memory_rebuild_app.unified_memory import UnifiedMemoryDatabase


def _db(tmp_path: Path) -> Path:
    db = tmp_path / "frozen" / "memory_jazn.sqlite3"
    assert UnifiedMemoryDatabase(db).initialize()["ok"]
    with closing(sqlite3.connect(db)) as con:
        for key, value in (
            ("memory_generation", "alpha"),
            ("restore_run_id", "synthetic-run"),
            ("source_union_sha256", "a"*64),
        ):
            con.execute("INSERT OR REPLACE INTO unified_memory_meta(key,value) VALUES (?,?)", (key, value))
        con.commit()
        con.execute("PRAGMA journal_mode=DELETE")
    return db


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_missing_independent_reference_is_unverified(tmp_path: Path) -> None:
    db = _db(tmp_path)
    result = verify_provenance_chain(db)
    assert result["state"] == "unverified"
    assert result["activation_authorized"] is False
    assert str(db) not in str(result)


def test_exact_independent_artifact_pin_is_verified_only_within_scope(tmp_path: Path) -> None:
    db = _db(tmp_path)
    independent = tmp_path / "operator-reference.sqlite3"
    shutil.copyfile(db, independent)
    result = verify_provenance_chain(db, reference=PinnedMemoryArtifact(independent, _hash(db)))
    assert result["state"] == "verified"
    assert result["artifact_verified"] is True
    assert result["historical_rebuild_verified"] is False
    assert result["parent_chain_verified"] is False
    assert result["activation_authorized"] is False


def test_pin_mismatch_is_conflict(tmp_path: Path) -> None:
    db = _db(tmp_path)
    result = verify_provenance_chain(db, reference=PinnedMemoryArtifact(db, "b"*64))
    assert result["state"] == "conflict"
    assert result["activation_authorized"] is False


def test_symlinked_reference_is_blocked(tmp_path: Path) -> None:
    db = _db(tmp_path)
    alias = tmp_path / "alias.sqlite3"
    try:
        alias.symlink_to(db)
    except (OSError, NotImplementedError):
        pytest.skip("no symlink capability")
    result = verify_provenance_chain(db, reference=PinnedMemoryArtifact(alias, _hash(db)))
    assert result["state"] == "blocked"


def test_beta_without_independent_parent_pin_remains_unverified(tmp_path: Path) -> None:
    db = _db(tmp_path)
    with closing(sqlite3.connect(db)) as con:
        for key, value in (
            ("memory_generation", "beta"), ("parent_database_sha256", "f"*64),
        ):
            con.execute("INSERT OR REPLACE INTO unified_memory_meta(key,value) VALUES (?,?)", (key, value))
        con.commit()
    reference = tmp_path / "reference.sqlite3"
    shutil.copyfile(db, reference)
    result = verify_provenance_chain(db, reference=PinnedMemoryArtifact(reference, _hash(db)))
    assert result["state"] == "unverified"
    assert result["issue"] == "independent_parent_missing"
    assert result["parent_chain_verified"] is False
    assert result["activation_authorized"] is False
