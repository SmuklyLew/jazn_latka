from __future__ import annotations

import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace

from latka_jazn.tools.chat_export_importer import ChatExportImporter
from latka_jazn.tools.memory_rebuild_app import build_source_union_manifest
from latka_jazn.tools.memory_rebuild_app.test_profiles import _unresolved_conflicts


CONVERSATION_ID = "conversation-source-union-fixture"


def _message(message_id: str, role: str, text: str, create_time: float) -> dict:
    return {
        "id": message_id,
        "author": {"role": role, "name": None, "metadata": {}},
        "create_time": create_time,
        "update_time": None,
        "content": {"content_type": "text", "parts": [text]},
        "status": "finished_successfully",
        "end_turn": True,
        "weight": 1.0,
        "metadata": {},
        "recipient": "all",
        "channel": None,
    }


def _node(
    node_id: str,
    *,
    parent: str | None,
    children: list[str],
    message: dict | None,
) -> dict:
    return {
        "id": node_id,
        "message": message,
        "parent": parent,
        "children": children,
    }


def _conversation(branch_node: str, branch_text: str) -> dict:
    return {
        "id": CONVERSATION_ID,
        "conversation_id": CONVERSATION_ID,
        "title": "source union fixture",
        "create_time": 1.0,
        "update_time": 3.0,
        "current_node": branch_node,
        "mapping": {
            "root": _node("root", parent=None, children=["user"], message=None),
            "user": _node(
                "user",
                parent="root",
                children=[branch_node],
                message=_message("message-user", "user", "Pytanie", 2.0),
            ),
            branch_node: _node(
                branch_node,
                parent="user",
                children=[],
                message=_message(f"message-{branch_node}", "assistant", branch_text, 3.0),
            ),
        },
    }


def _changed_same_node(text: str) -> dict:
    conversation = _conversation("assistant-a", text)
    conversation["mapping"]["assistant-a"]["message"]["id"] = "message-assistant-a"
    return conversation


def _write_export(path: Path, *conversations: dict) -> Path:
    path.write_text(
        json.dumps(list(conversations), ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    return path


def test_source_union_is_order_independent_and_reconstructs_cross_snapshot_branch_point(
    tmp_path: Path,
) -> None:
    source_a = _write_export(tmp_path / "snapshot-a.json", _conversation("assistant-a", "A"))
    source_b = _write_export(tmp_path / "snapshot-b.json", _conversation("assistant-b", "B"))

    forward = build_source_union_manifest([source_a, source_b])
    reverse = build_source_union_manifest([source_b, source_a])

    assert forward["ok"] is True
    assert reverse["ok"] is True
    assert forward["union_fingerprint_sha256"] == reverse["union_fingerprint_sha256"]
    assert forward["unique_conversation_count"] == 1
    assert forward["unique_conversation_variant_count"] == 2
    assert forward["union_node_count"] == 4
    assert forward["union_message_node_count"] == 3
    assert forward["union_branch_point_count"] == 1
    assert forward["branch_union_count"] == 1
    assert forward["projection_conflict_conversation_count"] == 0
    assert forward["requires_projection_resolution"] is False
    row = forward["conversations"][0]
    assert row["relation"] == "branch_union"
    assert row["union_branch_point_count"] == 1


def test_source_union_keeps_changed_shared_node_fail_closed(tmp_path: Path) -> None:
    source_a = _write_export(tmp_path / "snapshot-a.json", _changed_same_node("A"))
    source_changed = _write_export(
        tmp_path / "snapshot-changed.json",
        _changed_same_node("A — zmieniona treść"),
    )

    report = build_source_union_manifest([source_a, source_changed])

    assert report["ok"] is True
    assert report["projection_conflict_conversation_count"] == 1
    assert report["changed_message_node_count"] == 1
    assert report["requires_projection_resolution"] is True
    row = report["conversations"][0]
    assert row["relation"] == "conflict"
    assert row["changed_message_node_ids"] == ["assistant-a"]


def test_non_conversation_json_sidecar_is_not_promoted_to_chat_history(tmp_path: Path) -> None:
    source = _write_export(tmp_path / "conversations.json", _conversation("assistant-a", "A"))
    sidecar = tmp_path / "shared_conversations.json"
    sidecar.write_text(
        json.dumps(
            [
                {
                    "id": "shared-id",
                    "conversation_id": CONVERSATION_ID,
                    "title": "shared metadata",
                    "is_anonymous": True,
                }
            ]
        ),
        encoding="utf-8",
    )

    report = build_source_union_manifest([source, sidecar])

    assert report["unique_conversation_count"] == 1
    assert report["lossless_chat_source_count"] == 1
    assert report["ignored_non_chat_source_count"] == 1


def _archive_state(database: Path) -> dict:
    with sqlite3.connect(database) as con:
        node_ids = {
            str(row[0])
            for row in con.execute(
                "SELECT node_id FROM nodes WHERE conversation_id=?",
                (CONVERSATION_ID,),
            ).fetchall()
        }
        statuses = [
            str(row[0])
            for row in con.execute(
                "SELECT resolution_status FROM import_conflicts WHERE conversation_id=?",
                (CONVERSATION_ID,),
            ).fetchall()
        ]
        variants = int(
            con.execute(
                "SELECT COUNT(*) FROM conversation_variant_payloads WHERE conversation_id=?",
                (CONVERSATION_ID,),
            ).fetchone()[0]
        )
    return {"node_ids": node_ids, "statuses": statuses, "variants": variants}


def test_divergent_branches_are_preserved_without_becoming_unresolved_conflicts(
    tmp_path: Path,
) -> None:
    source_a = _write_export(tmp_path / "snapshot-a.json", _conversation("assistant-a", "A"))
    source_b = _write_export(tmp_path / "snapshot-b.json", _conversation("assistant-b", "B"))
    importer = ChatExportImporter()

    database_ab = tmp_path / "archive-ab.sqlite3"
    first_ab = importer.import_one(source_a, database_ab, full_validation=False)
    second_ab = importer.import_one(source_b, database_ab, full_validation=False)
    assert first_ab.ok is True
    assert second_ab.ok is True
    state_ab = _archive_state(database_ab)

    database_ba = tmp_path / "archive-ba.sqlite3"
    first_ba = importer.import_one(source_b, database_ba, full_validation=False)
    second_ba = importer.import_one(source_a, database_ba, full_validation=False)
    assert first_ba.ok is True
    assert second_ba.ok is True
    state_ba = _archive_state(database_ba)

    expected_nodes = {"root", "user", "assistant-a", "assistant-b"}
    assert state_ab["node_ids"] == expected_nodes
    assert state_ba["node_ids"] == expected_nodes
    assert state_ab["variants"] == 2
    assert state_ba["variants"] == 2
    assert state_ab["statuses"] == ["preserved_union"]
    assert state_ba["statuses"] == ["preserved_union"]

    unresolved_ab = _unresolved_conflicts(database_ab)
    unresolved_ba = _unresolved_conflicts(database_ba)
    assert unresolved_ab["chat_import_conflicts"] == 0
    assert unresolved_ba["chat_import_conflicts"] == 0
    assert unresolved_ab["preserved_chat_divergences"] == 1
    assert unresolved_ba["preserved_chat_divergences"] == 1


def test_import_many_preserves_operator_order_instead_of_sorting_by_file_size(
    tmp_path: Path,
    monkeypatch,
) -> None:
    small = tmp_path / "small.json"
    large = tmp_path / "large.json"
    small.write_text("[]", encoding="utf-8")
    large.write_text("[" + " " * 4096 + "]", encoding="utf-8")
    seen_sources: list[str] = []

    def fake_run(command, **_kwargs):
        source_index = command.index("--source") + 1
        seen_sources.append(command[source_index])
        return SimpleNamespace(returncode=1, stdout="", stderr="synthetic stop")

    monkeypatch.setattr("subprocess.run", fake_run)
    ChatExportImporter().import_many([small, large], tmp_path / "unused.sqlite3")

    assert seen_sources == [str(small.resolve()), str(large.resolve())]
