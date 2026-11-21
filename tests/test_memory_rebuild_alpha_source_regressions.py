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


def test_embedded_html_uses_streaming_path_and_preserves_entities(
    tmp_path: Path, monkeypatch,
) -> None:
    from latka_jazn.tools.memory_rebuild_app import html_import

    source = tmp_path / "chat.html"
    conversations = []
    for index in range(75):
        node_id = f"n-{index}"
        conversations.append({
            "id": f"synthetic-{index}",
            "title": "Rozmowa &amp; pamięć",
            "current_node": node_id,
            "mapping": {
                node_id: {
                    "id": node_id, "parent": None, "children": [],
                    "message": {
                        "id": f"message-{index}",
                        "author": {"role": "user"},
                        "content": {"content_type": "text", "parts": ["Test &amp; źródło"]},
                        "metadata": {},
                    },
                },
            },
        })
    source.write_text(
        "<html><script>var jsonData = " +
        json.dumps(conversations, ensure_ascii=False) +
        ";</script></html>",
        encoding="utf-8",
    )

    def forbidden_full_html_read(*_args, **_kwargs):
        raise AssertionError("embedded chat.html must not be loaded as one string")

    monkeypatch.setattr(html_import, "_read_html_source", forbidden_full_html_read)
    member, mode, warnings = html_import.inspect_html_source(source)
    assert member == "chat.html"
    assert mode == "embedded_json_lossless"
    assert not warnings

    rows = html_import.iter_html_conversations(source)
    first = next(rows)
    assert first["title"] == "Rozmowa & pamięć"
    assert first["mapping"]["n-0"]["message"]["content"]["parts"][0] == "Test & źródło"
    assert 1 + sum(1 for _ in rows) == 75

    database = tmp_path / "html-smoke.sqlite3"
    native = html_import.import_chat_html(source, database)
    assert native.conversations_seen == 75
    assert native.mode == "embedded_json_lossless"
    again = html_import.import_chat_html(source, database)
    assert again.mode == "identical_source_duplicate"
    assert again.conversations_seen == 75


def test_html_assignment_marker_crosses_read_chunk_boundary(tmp_path: Path) -> None:
    from latka_jazn.tools.memory_rebuild_app.html_import import iter_html_conversations

    path = tmp_path / "chat-marker-boundary.html"
    payload = [{
        "id": "boundary-conversation", "title": "Chunk test",
        "mapping": {}, "current_node": None,
    }]
    path.write_text(
        " " * (64 * 1024 - 7) +
        "<script>const jsonData = " +
        json.dumps(payload) + ";</script>",
        encoding="utf-8",
    )
    assert [item["id"] for item in iter_html_conversations(path)] == [
        "boundary-conversation"
    ]


def test_truncated_embedded_json_fails_without_partial_import(tmp_path: Path) -> None:
    import pytest
    from latka_jazn.tools.memory_rebuild_app.html_import import import_chat_html

    path = tmp_path / "chat-truncated.html"
    path.write_text(
        '<script>var jsonData = [{"id":"only-id","mapping":{}}, {"id":',
        encoding="utf-8",
    )
    with pytest.raises((ValueError, json.JSONDecodeError)):
        import_chat_html(path, tmp_path / "truncated.sqlite3")


def test_empty_embedded_conversations_are_rejected(tmp_path: Path) -> None:
    import pytest
    from latka_jazn.tools.memory_rebuild_app.html_import import import_chat_html

    html = tmp_path / "empty-chat.html"
    html.write_text("<script>var jsonData = [];</script>", encoding="utf-8")
    with pytest.raises(ValueError, match="html_contains_no_recoverable_conversations"):
        import_chat_html(html, tmp_path / "no-empty-import.sqlite3")


def test_unnumbered_music_analysis_edit_retains_revision_identity(
    tmp_path: Path,
) -> None:
    source = tmp_path / "analizy_utworow.json"
    adapter = MusicAnalysisAdapter()
    probe = SourceProbe(str(source), "music", 1.0, ())
    settings = MemoryRebuildSettings()

    source.write_text(
        json.dumps({"analizy": [{"tytul": "Wspólny tytuł", "emocje": "spokój"}]},
                   ensure_ascii=False),
        encoding="utf-8",
    )
    before = list(adapter.prepare(source, probe, settings).iter_records())
    source.write_text(
        json.dumps({"analizy": [{"tytul": "Wspólny tytuł", "emocje": "radość"}]},
                   ensure_ascii=False),
        encoding="utf-8",
    )
    after = list(adapter.prepare(source, probe, settings).iter_records())
    assert before[0].logical_key == after[0].logical_key
    assert before[0].content_sha256 != after[0].content_sha256
