from __future__ import annotations

import json
from pathlib import Path

import pytest

from latka_jazn.core.lexical_semantics import LexicalSemanticUnderstanding
from latka_jazn.core.polish_understanding import PolishUnderstandingEngine
from latka_jazn.db.shard_manifest import ShardManifestError, SQLiteShardManager
from latka_jazn.memory.conversation_archive import ConversationArchiveStore
from latka_jazn.memory.file_sync import MemoryFileSync
from latka_jazn.memory.grounded_reflection_store import GroundedReflectionStore
from latka_jazn.memory.importer import MemoryImporter
from latka_jazn.memory.memory_root import default_memory_root
from latka_jazn.memory.requirements_ledger import RequirementsLedger
from latka_jazn.memory.runtime_persistence import RuntimeMemoryWriter, scan_runtime_duplicates
from latka_jazn.version import PACKAGE_VERSION_FULL


def _runtime_root(tmp_path: Path) -> Path:
    root = tmp_path / "runtime_roots" / "jazn-v16310"
    root.mkdir(parents=True)
    return root


def _canonical_memory(root: Path) -> Path:
    memory = default_memory_root(root)
    memory.mkdir(parents=True, exist_ok=True)
    return memory


def test_release_version_tracks_v16322_active_runtime_subject_root_hardening() -> None:
    assert PACKAGE_VERSION_FULL == "16.3.23-persistent-runtime-lifecycle-observability-hardening"


def test_shard_manager_normalizes_legacy_memory_prefix_at_host_memory_root(
    tmp_path: Path,
) -> None:
    root = _runtime_root(tmp_path)
    memory = _canonical_memory(root)
    sqlite_dir = memory / "sqlite" / "runtime_write_v1"
    sqlite_dir.mkdir(parents=True)
    db_path = sqlite_dir / "runtime_memory.sqlite3"
    db_path.touch()
    manifest_path = sqlite_dir / "runtime_memory_shards.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "jazn_sqlite_shards/v1",
                "logical_database": "chat_context",
                "role": "canonical_runtime_conversation_memory",
                "active_write_shard": "0001",
                "max_file_bytes": 1024 * 1024,
                "shards": [
                    {
                        "shard_id": "0001",
                        "path": "memory/sqlite/runtime_write_v1/runtime_memory.sqlite3",
                        "role": "active_write",
                        "created_at_utc": "2026-08-26T00:00:00+00:00",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    manager = SQLiteShardManager(
        memory,
        "memory/sqlite/runtime_write_v1/runtime_memory_shards.json",
        logical_database="chat_context",
        role="canonical_runtime_conversation_memory",
        default_db_path="memory/sqlite/runtime_write_v1/runtime_memory.sqlite3",
    )

    manifest = manager.load_existing()
    assert manifest.shards[0].path == "sqlite/runtime_write_v1/runtime_memory.sqlite3"
    assert manifest.active_path(memory) == db_path.resolve()
    assert manager.manifest_path == manifest_path.resolve()
    assert "memory/memory" not in manager.active_path().as_posix()


def test_shard_manager_rejects_manifest_path_escape(tmp_path: Path) -> None:
    root = _runtime_root(tmp_path)
    memory = _canonical_memory(root)

    with pytest.raises(ShardManifestError):
        SQLiteShardManager(
            memory,
            "../outside.json",
            logical_database="chat_context",
            role="canonical_runtime_conversation_memory",
            default_db_path="sqlite/runtime_memory.sqlite3",
        )


def test_runtime_memory_writer_keeps_all_file_layers_in_host_memory_root(
    tmp_path: Path,
) -> None:
    root = _runtime_root(tmp_path)
    memory = _canonical_memory(root)

    writer = RuntimeMemoryWriter(root, version="16.3.10-host-memory-root-compat")

    assert writer.memory_root == memory.resolve()
    assert writer.journal.path.resolve() == (memory / "raw" / "dziennik.json").resolve()
    assert {item.path.parent.resolve() for item in writer.layers.values()} == {
        (memory / "layered").resolve()
    }
    assert not (root / "memory" / "layered").exists()


def test_runtime_duplicate_scan_reads_canonical_host_memory(tmp_path: Path) -> None:
    root = _runtime_root(tmp_path)
    memory = _canonical_memory(root)
    layered = memory / "layered"
    layered.mkdir(parents=True)
    payload = {"fingerprint": "same", "text": "x"}
    (layered / "episodic.jsonl").write_text(
        json.dumps(payload) + "\n" + json.dumps(payload) + "\n",
        encoding="utf-8",
    )

    report = scan_runtime_duplicates(root)

    assert report["files"]["layered/episodic.jsonl"]["exists"] is True
    assert report["files"]["layered/episodic.jsonl"]["duplicate_keys"] == {"same": 2}


def test_supporting_memory_components_share_canonical_host_root(tmp_path: Path) -> None:
    root = _runtime_root(tmp_path)
    memory = _canonical_memory(root)
    dummy_store = object()

    importer = MemoryImporter(dummy_store, root)  # type: ignore[arg-type]
    sync = MemoryFileSync(root, dummy_store)  # type: ignore[arg-type]
    requirements = RequirementsLedger(root)
    reflections = GroundedReflectionStore(root)

    assert importer.memory_root == memory.resolve()
    assert sync.memory_root == memory.resolve()
    assert requirements.path == memory / "layered" / "requirements_ledger_current_line.jsonl"
    assert reflections.path == memory / "layered" / "grounded_reflections.jsonl"
    assert not (root / "memory").exists()


def test_conversation_archive_uses_host_memory_sqlite_root(tmp_path: Path) -> None:
    root = _runtime_root(tmp_path)
    memory = _canonical_memory(root)

    archive = ConversationArchiveStore(root)

    assert archive.memory_root == memory.resolve()
    assert archive.archive_dir == memory / "sqlite" / "conversation_archive_v1"
    assert archive.fts_dir == memory / "sqlite" / "conversation_fts_v1"
    assert archive.staging_dir == memory / "sqlite" / "staging_v1"
    assert not (root / "memory" / "sqlite").exists()


def test_lexical_semantics_prefers_private_current_line_lexicon_in_host_memory(
    tmp_path: Path,
) -> None:
    root = _runtime_root(tmp_path)
    memory = _canonical_memory(root)
    raw = memory / "raw"
    raw.mkdir(parents=True)
    marker = {"marker": "private-current-line", "phrase_rules": [], "semantic_fields": {}}
    (raw / "semantic_lexicon_current_line.json").write_text(
        json.dumps(marker), encoding="utf-8"
    )

    engine = LexicalSemanticUnderstanding(root)

    assert engine.lexicon.get("marker") == "private-current-line"


def test_polish_understanding_reads_private_lexicon_from_host_memory(tmp_path: Path) -> None:
    root = _runtime_root(tmp_path)
    memory = _canonical_memory(root)
    raw = memory / "raw"
    raw.mkdir(parents=True)
    marker = {
        "marker": "private-polish",
        "lemma_aliases": {},
        "intent_rules": {},
        "need_patterns": [],
    }
    (raw / "POLISH_UNDERSTANDING_LEXICON.json").write_text(
        json.dumps(marker), encoding="utf-8"
    )

    engine = PolishUnderstandingEngine(root)

    assert engine.lexicon.get("marker") == "private-polish"
