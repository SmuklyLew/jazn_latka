from __future__ import annotations

from pathlib import Path
import json
import os

from latka_jazn.tools.memory_rebuild_app import unified_schema
from latka_jazn.tools.memory_rebuild_app.unified_memory import (
    CANONICAL_DATABASE_NAME,
    UnifiedMemoryDatabase,
)


def test_backup_releases_source_and_destination_handles_before_return(tmp_path: Path) -> None:
    database = tmp_path / CANONICAL_DATABASE_NAME
    store = UnifiedMemoryDatabase(database)
    assert store.initialize()["ok"]

    backup = store.backup(tmp_path / "memory-backup.sqlite3")
    assert backup.is_file()

    moved = tmp_path / "memory-backup-moved.sqlite3"
    os.replace(backup, moved)
    moved.unlink()

    assert not backup.exists()
    assert not moved.exists()


def test_unified_schema_public_exports_resolve_to_real_attributes() -> None:
    assert "LEGACY_DATABASE_NAMES" in unified_schema.__all__
    assert all(hasattr(unified_schema, name) for name in unified_schema.__all__)


def test_unified_import_preserves_message_metadata_attachments(tmp_path: Path) -> None:
    source = tmp_path / "conversations.json"
    database = tmp_path / CANONICAL_DATABASE_NAME
    source.write_text(
        json.dumps([
            {
                "id": "conversation-with-attachment",
                "title": "Załącznik w metadanych",
                "current_node": "message-node",
                "mapping": {
                    "root": {
                        "id": "root",
                        "parent": None,
                        "children": ["message-node"],
                        "message": None,
                    },
                    "message-node": {
                        "id": "message-node",
                        "parent": "root",
                        "children": [],
                        "message": {
                            "id": "message-1",
                            "author": {"role": "user"},
                            "create_time": 1.0,
                            "content": {"content_type": "text", "parts": ["Sprawdź załącznik."]},
                            "metadata": {
                                "attachments": [
                                    {
                                        "id": "file-attachment-1",
                                        "name": "pamięć.docx",
                                        "mimeType": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                                    }
                                ]
                            },
                        },
                    },
                },
            }
        ], ensure_ascii=False),
        encoding="utf-8",
    )

    store = UnifiedMemoryDatabase(database)
    result = store.import_sources([source])
    assert result["ok"], result

    with store.connect(read_only=True) as con:
        row = con.execute(
            "SELECT asset_pointer,original_filename,content_type,mime_type FROM assets WHERE asset_pointer=?",
            ("file-attachment-1",),
        ).fetchone()
        link_count = con.execute(
            "SELECT COUNT(*) FROM message_assets WHERE asset_pointer=?",
            ("file-attachment-1",),
        ).fetchone()[0]

    assert row is not None
    assert dict(row) == {
        "asset_pointer": "file-attachment-1",
        "original_filename": "pamięć.docx",
        "content_type": "attachment",
        "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }
    assert link_count == 1
