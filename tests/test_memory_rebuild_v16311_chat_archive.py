from __future__ import annotations

from pathlib import Path
import json
import sqlite3

from latka_jazn.tools.chat_export_importer import ChatExportImporter
from latka_jazn.tools.memory_rebuild_app import (
    RecallQuery,
    RecallStatus,
    TypedMemoryAPI,
    UnifiedMemoryDatabase,
    compare_chat_sources,
    list_chat_conversations,
)


def _message(mid: str, role: str, text: str, timestamp: float, *, hidden: bool = False, attachment: bool = False) -> dict:
    metadata: dict = {}
    if hidden:
        metadata["is_visually_hidden_from_conversation"] = True
    if attachment:
        metadata["attachments"] = [{
            "id": "file-book",
            "name": "pamietnik.docx",
            "mimeType": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        }]
    return {
        "id": mid,
        "author": {"role": role},
        "create_time": timestamp,
        "content": {"content_type": "text", "parts": [text]},
        "metadata": metadata,
        "recipient": "all",
        "channel": None,
    }


def _conversation(cid: str, user_text: str, assistant_text: str, *, hidden_assistant: bool = False) -> dict:
    root, user, assistant = f"{cid}-root", f"{cid}-user", f"{cid}-assistant"
    return {
        "id": cid,
        "title": f"Rozmowa {cid}",
        "create_time": 1767225600.0,
        "update_time": 1767225660.0,
        "current_node": assistant,
        "mapping": {
            root: {"id": root, "parent": None, "children": [user], "message": None},
            user: {
                "id": user,
                "parent": root,
                "children": [assistant],
                "message": _message(f"{cid}-mu", "user", user_text, 1767225601.0, attachment=True),
            },
            assistant: {
                "id": assistant,
                "parent": user,
                "children": [],
                "message": _message(
                    f"{cid}-ma", "assistant", assistant_text, 1767225602.0,
                    hidden=hidden_assistant,
                ),
            },
        },
    }


def _write_export(path: Path, conversations: list[dict]) -> None:
    path.write_text(json.dumps(conversations, ensure_ascii=False), encoding="utf-8")


def _write_embedded_html(path: Path, conversations: list[dict]) -> None:
    path.write_text(
        "<html><head></head><body><script>var jsonData = "
        + json.dumps(conversations, ensure_ascii=False)
        + ";</script></body></html>",
        encoding="utf-8",
    )


def test_chat_catalog_json_html_control_and_chat_by_chat_import(tmp_path: Path) -> None:
    conversations = [
        _conversation("chat-1", "Pamiętnik 2K25 jest ważnym projektem.", "ukryty-techniczny-token", hidden_assistant=True),
        _conversation("chat-2", "Druga pełna rozmowa bazowa.", "Zachowuję drugi kontekst."),
    ]
    source = tmp_path / "conversations.json"
    html = tmp_path / "chat.html"
    database = tmp_path / "memory_jazn.sqlite3"
    _write_export(source, conversations)
    _write_embedded_html(html, conversations)

    catalog = list_chat_conversations(source)
    assert catalog["ok"]
    assert catalog["conversation_count"] == 2
    assert {row["conversation_id"] for row in catalog["conversations"]} == {"chat-1", "chat-2"}

    comparison = compare_chat_sources(source, html)
    assert comparison["ok"]
    assert comparison["strict"]
    assert comparison["semantic_mismatches"] == []

    store = UnifiedMemoryDatabase(database)
    selective_import = getattr(store, "import_source_selected")
    first = selective_import(
        source,
        conversation_ids=["chat-1"],
        html_control=html,
    )
    assert first["ok"]
    assert first["selected_conversation_ids"] == ["chat-1"]

    with sqlite3.connect(database) as con:
        conversation_ids = {
            str(row[0]) for row in con.execute("SELECT DISTINCT conversation_id FROM memory_l0_conversations")
        }
        assert conversation_ids == {"chat-1"}
        visibility = dict(con.execute(
            "SELECT content,memory_eligible FROM memory_l0_records WHERE conversation_id='chat-1'"
        ))
        assert visibility["Pamiętnik 2K25 jest ważnym projektem."] == 1
        assert visibility["ukryty-techniczny-token"] == 0
        asset = con.execute(
            "SELECT original_filename,mime_type FROM memory_l0_assets WHERE asset_pointer='file-book'"
        ).fetchone()
        assert asset == (
            "pamietnik.docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )

    api = TypedMemoryAPI(database)
    visible = api.recall(RecallQuery(text="Pamiętnik 2K25"))
    assert visible.status is RecallStatus.EVIDENCE_FOUND
    hidden = api.recall(RecallQuery(text="ukryty-techniczny-token"))
    assert hidden.status is RecallStatus.UNKNOWN

    second = selective_import(source, conversation_ids=["chat-2"], html_control=html)
    assert second["ok"]
    with sqlite3.connect(database) as con:
        assert con.execute("SELECT COUNT(*) FROM memory_l0_conversations").fetchone()[0] == 2
        assert con.execute("SELECT COUNT(*) FROM memory_l0_imports").fetchone()[0] == 2


def test_rendered_html_fallback_is_not_accepted_as_lossless_control(tmp_path: Path) -> None:
    source = tmp_path / "conversations.json"
    html = tmp_path / "chat.html"
    _write_export(source, [_conversation("chat-1", "Treść źródłowa.", "Odpowiedź.")])
    html.write_text(
        '<div class="conversation"><h4>Rozmowa chat-1</h4>'
        '<pre class="message">Treść źródłowa.</pre><pre class="message">Odpowiedź.</pre></div>',
        encoding="utf-8",
    )
    comparison = compare_chat_sources(source, html)
    assert not comparison["ok"]
    assert not comparison["strict"]
    assert comparison["reason"] == "rendered_html_is_not_lossless_control"


def test_divergent_native_import_retains_variant_and_new_branch(tmp_path: Path) -> None:
    first = _conversation("branch-chat", "Początek rozmowy.", "Pierwsza odpowiedź.")
    second = json.loads(json.dumps(first))
    mapping = second["mapping"]
    assistant_id = "branch-chat-assistant"
    user_id = "branch-chat-user"
    mapping[assistant_id]["message"]["content"]["parts"] = ["Zmieniona odpowiedź w drugim eksporcie."]
    alt_id = "branch-chat-alt"
    mapping[alt_id] = {
        "id": alt_id,
        "parent": user_id,
        "children": [],
        "message": _message("branch-chat-alt-message", "assistant", "Alternatywna gałąź zachowana.", 1767225603.0),
    }
    mapping[user_id]["children"].append(alt_id)
    second["update_time"] = 1767225700.0

    source_a = tmp_path / "conversations-a.json"
    source_b = tmp_path / "conversations-b.json"
    database = tmp_path / "archive.sqlite3"
    _write_export(source_a, [first])
    _write_export(source_b, [second])

    importer = ChatExportImporter()
    assert importer.import_one(source_a, database).ok
    result = importer.import_one(source_b, database)
    assert result.ok
    assert result.conversation_counters.get("divergent") == 1

    with sqlite3.connect(database) as con:
        assert con.execute(
            "SELECT COUNT(*) FROM conversation_variant_payloads WHERE conversation_id='branch-chat'"
        ).fetchone()[0] == 2
        assert con.execute(
            "SELECT COUNT(*) FROM import_conflicts WHERE conversation_id='branch-chat'"
        ).fetchone()[0] == 1
        assert con.execute(
            "SELECT COUNT(*) FROM nodes WHERE conversation_id='branch-chat' AND node_id='branch-chat-alt'"
        ).fetchone()[0] == 1
