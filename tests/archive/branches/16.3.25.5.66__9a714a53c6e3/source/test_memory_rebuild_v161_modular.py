from __future__ import annotations

from pathlib import Path
import json
import sqlite3

import pytest

from latka_jazn.tools.memory_rebuild_app.adapters import default_adapter_registry
from latka_jazn.tools.memory_rebuild_app.embeddings import pack_vector
from latka_jazn.tools.memory_rebuild_app.l0_store import UnifiedL0Store
from latka_jazn.tools.memory_rebuild_app.settings import MemoryRebuildSettings
from latka_jazn.tools.memory_rebuild_app.theme import DEFAULT_THEME
from latka_jazn.tools.memory_rebuild_app.typed_api import (
    MemoryLayer, RecallQuery, RecallStatus, TypedMemoryAPI,
)
from latka_jazn.tools.memory_rebuild_app.unified_memory import UnifiedMemoryDatabase
from latka_jazn.tools.memory_rebuild_journal import JournalReader, JournalStore


def _message(mid: str, role: str, text: str, timestamp: float) -> dict:
    return {
        "id": mid,
        "author": {"role": role},
        "create_time": timestamp,
        "content": {"content_type": "text", "parts": [text]},
        "metadata": {},
    }


def _conversation(conversation_id: str, text: str) -> dict:
    root, user, assistant = f"{conversation_id}-root", f"{conversation_id}-u", f"{conversation_id}-a"
    return {
        "id": conversation_id,
        "title": f"Rozmowa {conversation_id}",
        "create_time": 1767225600.0,
        "update_time": 1767225660.0,
        "current_node": assistant,
        "mapping": {
            root: {"id": root, "parent": None, "children": [user], "message": None},
            user: {
                "id": user, "parent": root, "children": [assistant],
                "message": _message(f"{conversation_id}-mu", "user", text, 1767225601.0),
            },
            assistant: {
                "id": assistant, "parent": user, "children": [],
                "message": _message(f"{conversation_id}-ma", "assistant", "Zapisuję źródło.", 1767225602.0),
            },
        },
    }


def _journal(path: Path, record_id: str, content: str, event: str) -> None:
    path.write_text(json.dumps({
        "id": record_id,
        "title": "Ślad temporalny",
        "content": content,
        "data": event,
        "importance": 0.8,
    }, ensure_ascii=False) + "\n", encoding="utf-8")


def test_structure_settings_theme_and_adapter_contracts() -> None:
    assert len(Path("tools/rebuild_memory.py").read_text(encoding="utf-8").splitlines()) < 20
    assert len(Path("tools/memory_rebuild.py").read_text(encoding="utf-8").splitlines()) < 20
    assert DEFAULT_THEME.l0_label != DEFAULT_THEME.active_label
    assert len(default_adapter_registry().ids()) == 5
    assert MemoryRebuildSettings().require_fts5
    assert not MemoryRebuildSettings().embeddings_enabled
    with pytest.raises(ValueError, match="FTS5"):
        MemoryRebuildSettings(require_fts5=False)
    with pytest.raises(ValueError, match="automatyczne"):
        MemoryRebuildSettings(automatic_l3=True)


def test_all_format_adapters_feed_one_common_l0_database(tmp_path: Path) -> None:
    database = tmp_path / "memory_jazn.sqlite3"
    chat = tmp_path / "conversations.json"
    html = tmp_path / "chat.html"
    journal = tmp_path / "dziennik.jsonl"
    music = tmp_path / "analizy_utworow.json"
    chat.write_text(json.dumps([_conversation("json-chat", "Pamięć z JSON")], ensure_ascii=False), encoding="utf-8")
    html.write_text(
        '<div class="conversation"><h4>Rozmowa HTML</h4>'
        '<pre class="message">Pamięć z HTML</pre><pre class="message">Odpowiedź</pre></div>',
        encoding="utf-8",
    )
    _journal(journal, "journal-1", "Pamięć z dziennika", "2026-01-02T10:00:00+00:00")
    music.write_text(json.dumps({"analizy": [{
        "id": "song-1",
        "tytul": "Pieśń światła",
        "analiza": "Motyw światła i ciągłości pamięci.",
    }]}, ensure_ascii=False), encoding="utf-8")

    store = UnifiedMemoryDatabase(database)
    result = store.import_sources([chat, html, journal, music])
    assert result["ok"], json.dumps(result, ensure_ascii=False, indent=2, default=str)
    with sqlite3.connect(database) as con:
        kinds = dict(con.execute(
            "SELECT source_kind,COUNT(*) FROM memory_l0_records GROUP BY source_kind"
        ))
        adapters = int(con.execute("SELECT COUNT(DISTINCT adapter_id) FROM memory_l0_sources").fetchone()[0])
        music_count = int(con.execute("SELECT COUNT(*) FROM music_analysis_current").fetchone()[0])
        guard = con.execute(
            "SELECT automatic_l2,automatic_l3,automatic_activation,private_replacement_allowed "
            "FROM memory_activation_guard WHERE guard_id=1"
        ).fetchone()
    assert kinds["chatgpt_conversation"] >= 4
    assert kinds["journal"] == 1
    assert kinds["music_analysis"] == 1
    assert adapters == 4
    assert music_count == 1
    assert guard == (0, 0, 0, 0)
    assert not any((tmp_path / name).exists() for name in (
        "archive_chats.sqlite3", "journal.sqlite3", "experience.sqlite3", "import_catalog.sqlite3",
    ))


def test_common_l0_creates_revisions_instead_of_overwriting(tmp_path: Path) -> None:
    database = tmp_path / "memory_jazn.sqlite3"
    first = tmp_path / "dziennik-first.jsonl"
    second = tmp_path / "dziennik-second.jsonl"
    _journal(first, "same-entry", "Pierwsza wersja latarni.", "2026-01-01T10:00:00+00:00")
    _journal(second, "same-entry", "Druga wersja latarni z korektą.", "2026-01-01T10:00:00+00:00")
    store = UnifiedMemoryDatabase(database)
    assert store.import_sources([first])["ok"]
    assert store.import_sources([second])["ok"]
    assert store.import_sources([second])["ok"]
    with sqlite3.connect(database) as con:
        rows = con.execute(
            """SELECT revision,content,is_current_revision FROM memory_l0_records
               WHERE logical_key='journal:id:same-entry' ORDER BY revision"""
        ).fetchall()
    assert len(rows) == 2
    assert rows[0][0] == 1 and rows[0][2] == 0 and "Pierwsza wersja" in rows[0][1]
    assert rows[1][0] == 2 and rows[1][2] == 1 and "Druga wersja" in rows[1][1]


def test_typed_temporal_recall_provenance_and_truthful_unknown(tmp_path: Path) -> None:
    database = tmp_path / "memory_jazn.sqlite3"
    older = tmp_path / "dziennik-older.jsonl"
    newer = tmp_path / "dziennik-newer.jsonl"
    _journal(older, "older", "Latarnia z dawnego spaceru.", "2024-01-01T10:00:00+00:00")
    _journal(newer, "newer", "Latarnia z nowego spaceru.", "2026-01-01T10:00:00+00:00")
    store = UnifiedMemoryDatabase(database)
    assert store.import_sources([older, newer])["ok"]

    api = TypedMemoryAPI(database)
    response = api.recall(RecallQuery(
        text="latarnia spaceru",
        temporal_start="2025-01-01T00:00:00+00:00",
        temporal_end="2026-12-31T23:59:59+00:00",
    ))
    assert response.status is RecallStatus.EVIDENCE_FOUND
    assert response.known
    assert len(response.hits) == 1
    assert "nowego" in response.hits[0].content
    assert response.hits[0].citation.source_sha256
    assert response.hits[0].citation.adapter_id == "journal/v16.1"
    serialized = response.to_dict()
    assert serialized["status"] == "evidence_found"
    assert serialized["query"]["layers"] == ["l0"]
    assert serialized["hits"][0]["layer"] == "l0"

    unknown = api.recall(RecallQuery(text="jednorożec orbitalny bez źródła"))
    assert unknown.status is RecallStatus.UNKNOWN
    assert not unknown.known
    assert unknown.hits == ()

    with sqlite3.connect(database) as con:
        con.execute(
            """INSERT INTO memory_records(
               memory_id,tier,kind,content,content_sha256,domain,mode,truth_status,
               confidence,importance,created_at_utc,updated_at_utc,tags_json,record_json,active
               ) VALUES('active-1','working','note','Sekretaktywny tylko w pamięci aktywnej',
               'active-sha','test','explicit','user_confirmed',1.0,0.5,
               '2026-01-01T00:00:00+00:00','2026-01-01T00:00:00+00:00','[]','{}',1)"""
        )
        con.execute(
            """INSERT INTO memory_evidence(memory_id,evidence_key,source_type,source_id,evidence_json)
               VALUES('active-1','e1','manual_test','manual-source','{}')"""
        )
        con.commit()
    assert not api.recall(RecallQuery(text="sekretaktywny")).known
    explicit = api.recall(RecallQuery(
        text="sekretaktywny",
        layers=(MemoryLayer.ACTIVE,),
    ))
    assert explicit.known
    assert explicit.hits[0].layer is MemoryLayer.ACTIVE


class _FakeEmbeddingProvider:
    model_id = "test-embedding/v1"
    dimensions = 2

    def embed(self, texts):
        return [(1.0, 0.0) for _ in texts]


def test_embeddings_are_optional_and_require_explicit_configuration(tmp_path: Path) -> None:
    database = tmp_path / "memory_jazn.sqlite3"
    journal = tmp_path / "dziennik-embedding.jsonl"
    _journal(journal, "embedding", "Kot Tayfa odpoczywa przy oknie.", "2026-01-01T00:00:00+00:00")
    store = UnifiedMemoryDatabase(database)
    assert store.import_sources([journal])["ok"]
    with sqlite3.connect(database) as con:
        record_id = str(con.execute(
            "SELECT record_id FROM memory_l0_records WHERE is_current_revision=1"
        ).fetchone()[0])
        assert con.execute("SELECT COUNT(*) FROM memory_l0_embeddings").fetchone()[0] == 0
    UnifiedL0Store(database).store_embedding(record_id, "test-embedding/v1", pack_vector((1.0, 0.0)), 2)

    with pytest.raises(ValueError, match="Embedding retrieval"):
        TypedMemoryAPI(database).recall(RecallQuery(text="Tayfa", use_embeddings=True))
    settings = MemoryRebuildSettings(embeddings_enabled=True, embedding_model="test-embedding/v1")
    response = TypedMemoryAPI(
        database,
        settings=settings,
        embedding_provider=_FakeEmbeddingProvider(),
    ).recall(RecallQuery(text="Tayfa", use_embeddings=True))
    assert response.known
    assert response.hits[0].score > 0.0


def test_legacy_sqlite_adapter_is_read_only_and_feeds_common_model(tmp_path: Path) -> None:
    source_json = tmp_path / "dziennik-legacy-source.jsonl"
    legacy_root = tmp_path / "legacy"
    legacy_root.mkdir()
    legacy = legacy_root / "journal.sqlite3"
    _journal(source_json, "legacy-entry", "Zachowany wpis legacy.", "2025-01-01T00:00:00+00:00")
    with JournalStore(legacy) as journal_store:
        journal_store.import_reader(JournalReader(source_json))
    before = legacy.read_bytes()

    target = tmp_path / "memory_jazn.sqlite3"
    result = UnifiedMemoryDatabase(target).import_sources([legacy])
    assert result["ok"], json.dumps(result, ensure_ascii=False, indent=2, default=str)
    assert legacy.read_bytes() == before
    with sqlite3.connect(target) as con:
        assert con.execute(
            "SELECT COUNT(*) FROM memory_l0_records WHERE source_kind='legacy_sqlite'"
        ).fetchone()[0] >= 1
        assert con.execute("SELECT COUNT(*) FROM journal_entries").fetchone()[0] == 1
