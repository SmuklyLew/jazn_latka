from __future__ import annotations

from pathlib import Path
import json

from latka_jazn.tools.memory_rebuild_app.typed_api import MemoryLayer, RecallQuery, TypedMemoryAPI
from latka_jazn.tools.memory_rebuild_app.unified_memory import UnifiedMemoryDatabase
from latka_jazn.tools.memory_rebuild_common import fts_queries


def _message(mid: str, role: str, text: str, timestamp: float) -> dict:
    return {
        "id": mid,
        "author": {"role": role},
        "create_time": timestamp,
        "content": {"content_type": "text", "parts": [text]},
        "metadata": {},
    }


def _noise_conversations(count: int = 30) -> list[dict]:
    conversations: list[dict] = []
    for index in range(count):
        user_id = f"u-{index}"
        assistant_id = f"a-{index}"
        text = (
            "pełnego pliku dziennik wszystkie wpisy; "
            "Grubson Nasza Generacja; techniczna kopia rozmowy "
            f"{index}"
        )
        conversations.append(
            {
                "id": f"noise-{index}",
                "title": f"Kopia techniczna {index}",
                "create_time": 100.0 + index,
                "update_time": 101.0 + index,
                "current_node": assistant_id,
                "mapping": {
                    user_id: {
                        "id": user_id,
                        "parent": None,
                        "children": [assistant_id],
                        "message": _message(user_id, "user", text, 100.0 + index),
                    },
                    assistant_id: {
                        "id": assistant_id,
                        "parent": user_id,
                        "children": [],
                        "message": _message(
                            assistant_id,
                            "assistant",
                            "Powtórzenie indeksowe: " + text,
                            101.0 + index,
                        ),
                    },
                },
            }
        )
    return conversations


def test_polish_query_variants_and_bm25_direction() -> None:
    variants = fts_queries("pełnego pliku dziennik wszystkie wpisy")
    assert any("pełn*" in item and " OR " in item for item in variants)
    assert TypedMemoryAPI._score(-2.0) > TypedMemoryAPI._score(-1.0)
    assert TypedMemoryAPI._score(-1.0) > TypedMemoryAPI._score(0.0)


def test_structured_journal_and_music_survive_noisy_conversation_recall(tmp_path: Path) -> None:
    database = tmp_path / "memory_jazn.sqlite3"
    chats = tmp_path / "conversations.json"
    journal = tmp_path / "dziennik.json"
    music = tmp_path / "analizy_utworow.json"

    chats.write_text(json.dumps(_noise_conversations(), ensure_ascii=False), encoding="utf-8")
    journal.write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "id": "journal-611",
                        "tytuł": "Aktualizacja dziennika",
                        "wspomnienie": "Analiza pełnego pliku dziennik.json po połączeniu źródeł.",
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    music.write_text(
        json.dumps(
            {
                "analizy": [
                    {
                        "id": "music-grubson",
                        "wykonawca": "Grubson",
                        "tytuł": "Nasza Generacja",
                        "emocje": "Wzrost, nadzieja",
                        "warstwa_emocjonalna": {
                            "odczucie": "świeżość i przypływ odwagi"
                        },
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    store = UnifiedMemoryDatabase(database)
    result = store.import_sources([chats, journal, music])
    assert result["ok"], result

    api = TypedMemoryAPI(database)

    journal_response = api.recall(
        RecallQuery(
            text="pełnego pliku dziennik wszystkie wpisy",
            layers=(MemoryLayer.L0,),
            limit=20,
            require_provenance=True,
            use_embeddings=False,
        )
    )
    assert any(
        hit.record_kind == "journal_entry"
        and "pełnego pliku dziennik.json" in hit.content.casefold()
        for hit in journal_response.hits
    )

    music_response = api.recall(
        RecallQuery(
            text="Grubson Nasza Generacja",
            layers=(MemoryLayer.L0,),
            limit=20,
            require_provenance=True,
            use_embeddings=False,
        )
    )
    assert any(
        hit.record_kind == "music_analysis"
        and "wzrost, nadzieja" in hit.content.casefold()
        and "świeżość i przypływ odwagi" in hit.content.casefold()
        for hit in music_response.hits
    )
