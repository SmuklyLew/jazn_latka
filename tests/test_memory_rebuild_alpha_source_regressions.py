"""Synthetic regressions for ChatGPT archive and music import identity.

No private ChatGPT export, journal, or autobiographical MEMORY is used here.
"""

from __future__ import annotations

import json
from pathlib import Path

from latka_jazn.tools.chat_export_reader import build_conversation_graph
from latka_jazn.tools.memory_rebuild_app.adapters.common import conversation_records
from latka_jazn.tools.memory_rebuild_app.adapters.music_analysis import MusicAnalysisAdapter
from latka_jazn.tools.memory_rebuild_app.settings import MemoryRebuildSettings
from latka_jazn.tools.memory_rebuild_app.source_detection import SourceProbe


def test_non_dialogue_content_types_preserve_archive_but_not_memory_eligibility() -> None:
    types = (
        "text", "multimodal_text", "thoughts", "reasoning_recap",
        "code", "execution_output",
    )
    mapping = {}
    previous = None
    for index, content_type in enumerate(types):
        node_id = f"node-{index}"
        mapping[node_id] = {
            "id": node_id,
            "parent": previous,
            "children": [],
            "message": {
                "id": f"msg-{index}",
                "author": {"role": "assistant"},
                "channel": "final",
                "content": {"content_type": content_type, "parts": [f"synthetic-{index}"]},
                "metadata": {},
            },
        }
        if previous is not None:
            mapping[previous]["children"].append(node_id)
        previous = node_id
    graph = build_conversation_graph({
        "id": "synthetic-conversation",
        "title": "Synthetic source",
        "current_node": previous,
        "mapping": mapping,
    })
    assert len(graph.nodes) == len(types)
    records = list(conversation_records([graph]))
    assert len(records) == len(types)
    eligibility = {row.raw["content_type"]: row.raw["memory_eligible"] for row in records}
    assert eligibility["text"] is True
    assert eligibility["multimodal_text"] is True
    for technical in ("thoughts", "reasoning_recap", "code", "execution_output"):
        assert eligibility[technical] is False
        row = next(item for item in records if item.raw["content_type"] == technical)
        assert row.raw["visibility"] == "non_dialogue"
        assert row.importance <= 0.05


def test_numbered_music_analyses_with_same_title_do_not_overwrite(tmp_path: Path) -> None:
    source = tmp_path / "analizy_utworow.json"
    source.write_text(json.dumps({
        "analizy": [
            {"numer": 1, "tytul": "Ten sam tytuł", "analiza": "Pierwsza"},
            {"numer": 2, "tytul": "Ten sam tytuł", "analiza": "Druga"},
            {"numer": 3, "tytul": "Inny tytuł", "analiza": "Trzecia"},
        ]
    }, ensure_ascii=False), encoding="utf-8")
    prepared = MusicAnalysisAdapter().prepare(
        source, SourceProbe(str(source), "music", 1.0, ()), MemoryRebuildSettings(),
    )
    records = list(prepared.iter_records())
    assert len(records) == 3
    assert len({row.logical_key for row in records}) == 3
    assert {row.raw["numer"] for row in records} == {1, 2, 3}
    assert [row.title for row in records[:2]] == ["Ten sam tytuł"] * 2


def test_unnumbered_music_analyses_with_same_title_preserve_distinct_text(tmp_path: Path) -> None:
    source = tmp_path / "analysis_songs.json"
    source.write_text(json.dumps({"analizy": [
        {"tytul": "Tytuł", "analiza": "Wariant A"},
        {"tytul": "Tytuł", "analiza": "Wariant B"},
    ]}, ensure_ascii=False), encoding="utf-8")
    prepared = MusicAnalysisAdapter().prepare(
        source, SourceProbe(str(source), "music", 1.0, ()), MemoryRebuildSettings(),
    )
    records = list(prepared.iter_records())
    assert len(records) == 2
    assert records[0].logical_key != records[1].logical_key
