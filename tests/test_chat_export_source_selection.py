from __future__ import annotations

from pathlib import Path
import json
import zipfile

import pytest

from latka_jazn.tools.chat_export_importer import ChatExportImporter
from latka_jazn.tools.chat_export_reader import ChatExportReader


def _conversation(conversation_id: str, text: str = "ważna wiadomość") -> dict:
    return {
        "id": conversation_id,
        "title": f"Rozmowa {conversation_id}",
        "create_time": 100.0,
        "update_time": 102.0,
        "current_node": "message",
        "mapping": {
            "root": {"id": "root", "parent": None, "children": ["message"], "message": None},
            "message": {
                "id": "message",
                "parent": "root",
                "children": [],
                "message": {
                    "id": f"message-{conversation_id}",
                    "author": {"role": "user"},
                    "create_time": 101.0,
                    "content": {"content_type": "text", "parts": [text]},
                    "metadata": {},
                },
            },
        },
    }


def _write_zip(path: Path, members: dict[str, object]) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, value in members.items():
            if isinstance(value, str):
                archive.writestr(name, value)
            else:
                archive.writestr(name, json.dumps(value, ensure_ascii=False))


def _shared_record(conversation_id: str) -> dict:
    return {
        "id": f"share-{conversation_id}",
        "conversation_id": conversation_id,
        "title": "Udostępniony link",
        "is_anonymous": True,
    }


def test_shared_conversations_is_metadata_not_canonical_history(tmp_path: Path) -> None:
    source = tmp_path / "shared-only.zip"
    _write_zip(source, {"shared_conversations.json": [_shared_record("conv-shared")]})

    with ChatExportReader(source) as reader:
        assert reader.info.conversations_member is None
        assert reader.info.shared_metadata_only is True
        report = reader.inspect()
        assert report.ok is False
        assert report.shared_conversation_member_count == 1
        assert "shared-link metadata" in report.errors[0]
        with pytest.raises(ValueError, match="shared-link metadata"):
            list(reader.iter_graphs())

    database = tmp_path / "archive.sqlite3"
    with pytest.raises(ValueError, match="shared-link metadata"):
        ChatExportImporter().plan(source, database)


def test_exact_conversations_wins_over_shared_metadata(tmp_path: Path) -> None:
    source = tmp_path / "mixed.zip"
    _write_zip(
        source,
        {
            "shared_conversations.json": [_shared_record("conv-1")],
            "nested/conversations.json": [_conversation("conv-1")],
        },
    )

    with ChatExportReader(source) as reader:
        assert reader.info.conversation_members == ("nested/conversations.json",)
        assert reader.info.shared_conversations_members == ("shared_conversations.json",)
        graphs = list(reader.iter_graphs())
        assert [graph.conversation_id for graph in graphs] == ["conv-1"]
        assert graphs[0].message_count == 1


def test_numbered_conversation_files_are_all_read_in_numeric_order(tmp_path: Path) -> None:
    source = tmp_path / "numbered.zip"
    _write_zip(
        source,
        {
            "conversations-010.json": [_conversation("conv-10")],
            "conversations-002.json": [_conversation("conv-2")],
            "conversations-001.json": [_conversation("conv-1")],
            "shared_conversations.json": [_shared_record("conv-1")],
        },
    )

    with ChatExportReader(source) as reader:
        assert reader.info.conversation_members == (
            "conversations-001.json",
            "conversations-002.json",
            "conversations-010.json",
        )
        assert [graph.conversation_id for graph in reader.iter_graphs()] == ["conv-1", "conv-2", "conv-10"]


def test_suffix_collision_is_not_treated_as_conversations_json(tmp_path: Path) -> None:
    source = tmp_path / "suffix-collision.zip"
    _write_zip(
        source,
        {
            "my_conversations.json": [_conversation("wrong")],
            "shared_conversations.json": [_shared_record("shared")],
        },
    )
    with ChatExportReader(source) as reader:
        assert reader.info.conversation_members == ()
        assert reader.info.shared_metadata_only is True


def test_metadata_records_inside_canonical_file_are_skipped_and_reported(tmp_path: Path) -> None:
    source = tmp_path / "mixed-records.zip"
    _write_zip(
        source,
        {
            "conversations.json": [
                _shared_record("metadata-only"),
                _conversation("valid"),
            ]
        },
    )
    with ChatExportReader(source) as reader:
        graphs = list(reader.iter_graphs())
        assert [graph.conversation_id for graph in graphs] == ["valid"]
        assert len(reader.record_warnings) == 1
    with ChatExportReader(source) as reader:
        report = reader.inspect()
        assert report.ok
        assert report.skipped_metadata_record_count == 1
        assert report.conversation_count == 1
        assert report.warnings


def test_identical_duplicate_across_numbered_files_is_deduplicated(tmp_path: Path) -> None:
    source = tmp_path / "duplicate.zip"
    conversation = _conversation("same")
    _write_zip(
        source,
        {
            "conversations-001.json": [conversation],
            "conversations-002.json": [conversation],
        },
    )
    with ChatExportReader(source) as reader:
        graphs = list(reader.iter_graphs())
        assert len(graphs) == 1
        assert "identical duplicate" in reader.record_warnings[0]


def test_divergent_duplicate_across_numbered_files_is_blocked(tmp_path: Path) -> None:
    source = tmp_path / "divergent.zip"
    _write_zip(
        source,
        {
            "conversations-001.json": [_conversation("same", "pierwsza wersja")],
            "conversations-002.json": [_conversation("same", "inna wersja")],
        },
    )
    with ChatExportReader(source) as reader:
        with pytest.raises(ValueError, match="divergent duplicate"):
            list(reader.iter_graphs())


def test_direct_shared_json_is_not_importable_as_chat_history(tmp_path: Path) -> None:
    source = tmp_path / "shared_conversations.json"
    source.write_text(json.dumps([_shared_record("shared")]), encoding="utf-8")
    with ChatExportReader(source) as reader:
        assert reader.info.shared_metadata_only
        assert not reader.info.has_canonical_conversations
        assert not reader.inspect().ok


def test_json_probe_is_streaming_and_distinguishes_source_kinds(tmp_path: Path) -> None:
    from latka_jazn.tools.chat_export_reader import probe_json_source_kind

    conversation = tmp_path / "large-conversations.json"
    conversation.write_text(json.dumps([_conversation("conv")]), encoding="utf-8")
    shared = tmp_path / "arbitrary-shared.json"
    shared.write_text(json.dumps([_shared_record("shared")]), encoding="utf-8")
    journal = tmp_path / "journal.json"
    journal.write_text(json.dumps({"entries": [{"id": "entry", "content": "tekst"}]}), encoding="utf-8")

    assert probe_json_source_kind(conversation) == "conversation"
    assert probe_json_source_kind(shared) == "shared_metadata"
    assert probe_json_source_kind(journal) == "other"
