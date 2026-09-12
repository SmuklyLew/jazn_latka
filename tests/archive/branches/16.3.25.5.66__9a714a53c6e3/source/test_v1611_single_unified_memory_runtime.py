from __future__ import annotations

from hashlib import sha256
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
import os
import sqlite3

import pytest

from latka_jazn.memory.living_memory_gateway import LivingMemoryGateway
from latka_jazn.memory.memory_tier_core_store import MemoryTierCoreStore
from latka_jazn.memory.unified_memory_runtime import probe_unified_memory_database
from latka_jazn.tools.memory_rebuild_app import UnifiedMemoryDatabase


def _record(database: Path, memory_id: str, content: str, created: str) -> None:
    with closing(sqlite3.connect(database)) as con:
        con.execute(
            """INSERT INTO memory_records(
                 memory_id,tier,kind,content,content_sha256,domain,mode,truth_status,
                 confidence,importance,created_at_utc,updated_at_utc,tags_json,record_json,active
               ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)""",
            (
                memory_id,
                "short_term",
                "fact",
                content,
                sha256(content.encode("utf-8")).hexdigest(),
                "relationship",
                "source_grounded",
                "source_recorded",
                0.84,
                0.77,
                created,
                created,
                "[]",
                "{}",
            ),
        )
        con.commit()


def _plan(query: str, mode: str = "semantic_query") -> SimpleNamespace:
    return SimpleNamespace(search_mode=mode, search_terms=query.split())


def test_native_unified_identity_fts_recall_and_evidence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    database = tmp_path / "memory_jazn.sqlite3"
    UnifiedMemoryDatabase(database).initialize()
    _record(database, "m-early", "Pierwsza rozmowa o Katedrze", "2025-01-01T00:00:00+00:00")
    _record(database, "m-late", "Nowsza rozmowa o ogrodzie", "2026-01-01T00:00:00+00:00")
    with closing(sqlite3.connect(database)) as con:
        con.execute(
            "INSERT INTO memory_evidence(memory_id,evidence_key,source_type,source_id,evidence_json) VALUES(?,?,?,?,?)",
            ("m-early", "ev-1", "conversation_node", "node-7", "{}"),
        )
        con.commit()
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    monkeypatch.setenv("JAZN_MEMORY_SOURCE_ROOTS", str(database))

    gateway = LivingMemoryGateway(runtime)
    readiness = gateway.readiness()
    result = gateway.search(_plan("Katedrze"), limit=4)
    earliest = gateway.search(_plan("ignored", "chronological_earliest"), limit=1)

    assert readiness["status"] == "ready_native_unified"
    assert readiness["memory_search_ready"] is True
    assert readiness["selected_source_count"] == 1
    assert result["status"] == "ready_native_unified"
    assert result["hits"][0]["record_id"] == "m-early"
    assert result["hits"][0]["metadata"]["search_index"] == "memory_records_fts"
    assert result["hits"][0]["metadata"]["evidence"] == [
        {"evidence_id": "ev-1", "source_type": "conversation_node", "source_id": "node-7"}
    ]
    assert earliest["hits"][0]["record_id"] == "m-early"


def test_only_one_native_database_is_selected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    first = tmp_path / "first" / "memory_jazn.sqlite3"
    second = tmp_path / "second" / "memory_jazn.sqlite3"
    UnifiedMemoryDatabase(first).initialize()
    UnifiedMemoryDatabase(second).initialize()
    _record(first, "from-first", "Jedyny wybrany kanon", "2025-01-01T00:00:00+00:00")
    _record(second, "from-second", "Drugi kanon nie może dołączyć", "2025-01-02T00:00:00+00:00")
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    monkeypatch.setenv("JAZN_MEMORY_SOURCE_ROOTS", os.pathsep.join((str(first), str(second))))

    result = LivingMemoryGateway(runtime).search(_plan("kanon"), limit=8)

    assert result["counts"]["sources_recall_ready"] == 1
    assert {hit["record_id"] for hit in result["hits"]} == {"from-first"}
    assert sum(bool(source["selected_canonical"]) for source in result["sources"]) == 1


def test_v24_is_read_only_compatible_without_claiming_v25_fts(tmp_path: Path) -> None:
    database = tmp_path / "memory_jazn.sqlite3"
    UnifiedMemoryDatabase(database).initialize()
    _record(database, "legacy-native", "Zgodna pamięć v2.4", "2025-01-01T00:00:00+00:00")
    with closing(sqlite3.connect(database)) as con:
        con.execute("DROP TRIGGER memory_records_fts_insert")
        con.execute("DROP TRIGGER memory_records_fts_delete")
        con.execute("DROP TRIGGER memory_records_fts_update")
        con.execute("DROP TABLE memory_records_fts")
        con.execute(
            "UPDATE unified_memory_meta SET value='jazn_unified_memory/v2.4' WHERE key='schema_version'"
        )
        con.commit()

    report = probe_unified_memory_database(database)

    assert report["schema_identity"] == "jazn_unified_memory/v2.4"
    assert report["memory_search_ready"] is True
    assert "memory_records_fts" not in report["fts_counts"]


def test_corrupt_or_foreign_key_invalid_native_database_fails_closed(tmp_path: Path) -> None:
    corrupt = tmp_path / "corrupt.sqlite3"
    corrupt.write_bytes(b"not sqlite")
    assert probe_unified_memory_database(corrupt)["memory_search_ready"] is False

    invalid = tmp_path / "invalid" / "memory_jazn.sqlite3"
    UnifiedMemoryDatabase(invalid).initialize()
    with closing(sqlite3.connect(invalid)) as con:
        con.execute("PRAGMA foreign_keys=OFF")
        con.execute(
            "INSERT INTO memory_evidence(memory_id,evidence_key,source_type,source_id,evidence_json) VALUES(?,?,?,?,?)",
            ("missing", "ev-invalid", "source", "missing", "{}"),
        )
        con.commit()
    report = probe_unified_memory_database(invalid)
    assert report["memory_search_ready"] is False
    assert report["foreign_key_error_count"] == 1


def test_legacy_migration_is_snapshot_atomic_idempotent_and_closes_handles(tmp_path: Path) -> None:
    legacy = tmp_path / "legacy" / "memory_jazn.sqlite3"
    store = MemoryTierCoreStore(legacy)
    store.close()
    _record(legacy, "legacy-1", "Źródło pozostaje tylko do odczytu", "2025-01-01T00:00:00+00:00")
    source_before = sha256(legacy.read_bytes()).hexdigest()
    target = tmp_path / "target" / "memory_jazn.sqlite3"
    unified = UnifiedMemoryDatabase(target)

    first = unified.migrate_databases([legacy])
    second = unified.migrate_databases([legacy])

    assert first["ok"] is True
    assert first["atomic_replace"] is True
    assert first["source_databases_modified"] is False
    assert second["rows_copied"].get("memory_records", 0) == 0
    assert unified.stats()["memory_records"] == 1
    assert sha256(legacy.read_bytes()).hexdigest() == source_before
    legacy.rename(legacy.with_name("legacy-renamed.sqlite3"))
    target.rename(target.with_name("memory-renamed.sqlite3"))


def test_failed_snapshot_migration_preserves_existing_target(tmp_path: Path) -> None:
    target = tmp_path / "memory_jazn.sqlite3"
    UnifiedMemoryDatabase(target).initialize()
    _record(target, "stable", "Stabilny cel", "2025-01-01T00:00:00+00:00")
    before = sha256(target.read_bytes()).hexdigest()
    corrupt = tmp_path / "corrupt.sqlite3"
    corrupt.write_bytes(b"not sqlite")

    with pytest.raises(sqlite3.DatabaseError):
        UnifiedMemoryDatabase(target).migrate_databases([corrupt])

    assert sha256(target.read_bytes()).hexdigest() == before
    assert UnifiedMemoryDatabase(target).stats()["memory_records"] == 1
