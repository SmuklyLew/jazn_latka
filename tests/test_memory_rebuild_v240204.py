from __future__ import annotations

from pathlib import Path
import importlib.util
import json
import sys
import zipfile

import pytest

from latka_jazn.tools.memory_rebuild_coordinator import detect_source
from latka_jazn.tools.memory_restore import (
    DEVELOPER_CONFIRMATION,
    MemoryRestoreOrchestrator,
    MemoryRestoreSettings,
    RestoreSource,
)


def _message(message_id: str, role: str, text: str, timestamp: float) -> dict:
    return {
        "id": message_id,
        "author": {"role": role},
        "create_time": timestamp,
        "content": {"content_type": "text", "parts": [text]},
        "metadata": {},
    }


def _conversation(conversation_id: str, *, extended: bool = False) -> dict:
    mapping = {
        "root": {"id": "root", "parent": None, "children": ["user"], "message": None},
        "user": {
            "id": "user",
            "parent": "root",
            "children": ["assistant"] if extended else [],
            "message": _message(f"{conversation_id}-user", "user", "Ważne wydarzenie.", 101.0),
        },
    }
    current = "user"
    update = 102.0
    if extended:
        mapping["assistant"] = {
            "id": "assistant",
            "parent": "user",
            "children": [],
            "message": _message(
                f"{conversation_id}-assistant",
                "assistant",
                "Późniejsza część tej samej rozmowy.",
                103.0,
            ),
        }
        current = "assistant"
        update = 104.0
    return {
        "id": conversation_id,
        "title": f"Rozmowa {conversation_id}",
        "create_time": 100.0,
        "update_time": update,
        "current_node": current,
        "mapping": mapping,
    }


def _write_zip(path: Path, members: dict[str, object]) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, value in members.items():
            archive.writestr(name, json.dumps(value, ensure_ascii=False))


def _settings(source: Path, target: Path) -> MemoryRestoreSettings:
    return MemoryRestoreSettings(
        source_directory=str(source),
        target_root=str(target),
        mode="developer",
        create_backup=False,
        verify_after_each=False,
        full_validation=False,
        audit_classifiers=False,
        reclassify_journal_dry_run=False,
    )


def test_plan_simulates_previous_exports_in_temporary_database(tmp_path: Path) -> None:
    source = tmp_path / "exports"
    source.mkdir()
    first = source / "chatGPT-export-2025.07.18.zip"
    second = source / "chatGPT-export-2025.07.19.zip"
    _write_zip(first, {"conversations.json": [_conversation("same")]})
    _write_zip(second, {"conversations.json": [_conversation("same", extended=True)]})
    target = tmp_path / "test_03"

    plan = MemoryRestoreOrchestrator(
        _settings(source, target), tool_root=tmp_path / "repo"
    ).plan([first, second])

    assert plan.ok
    plan_payload = plan.to_dict()
    assert plan_payload["automatic_experience_approval"] is False
    assert plan_payload["automatic_l2"] is False
    assert plan_payload["automatic_l3"] is False
    assert plan_payload["media_analysis_enabled"] is False
    assert plan_payload["media_analysis_supported"] is False
    assert plan.chats[0]["plan"]["conversation_counters"] == {"new": 1}
    assert plan.chats[1]["plan"]["conversation_counters"] == {"extends_active": 1}
    assert plan.chats[1]["temporary_simulation"]["updated_conversations"] == 1
    assert not target.exists(), "plan may write only to its temporary database"


def test_shared_link_metadata_is_rejected_without_creating_empty_chat(tmp_path: Path) -> None:
    source = tmp_path / "exports"
    source.mkdir()
    shared = source / "shared-only.zip"
    _write_zip(
        shared,
        {
            "shared_conversations.json": [
                {
                    "id": "share-id",
                    "conversation_id": "conversation-id",
                    "title": "Udostępniony link",
                    "is_anonymous": True,
                }
            ]
        },
    )
    target = tmp_path / "test_03"
    orchestrator = MemoryRestoreOrchestrator(
        _settings(source, target), tool_root=tmp_path / "repo"
    )

    detected = detect_source(shared)
    plan = orchestrator.plan([shared])

    assert detected["shared_metadata_only"] is True
    assert detected["canonical_conversations_available"] is False
    assert not plan.ok
    assert plan.chats == []
    assert plan.rejected[0]["reason"] == "shared_conversations_metadata_only"
    assert not target.exists()


def test_numbered_conversation_json_members_are_one_lossless_source(tmp_path: Path) -> None:
    source = tmp_path / "exports"
    source.mkdir()
    export = source / "chatGPT-export-2026.07.19.zip"
    _write_zip(
        export,
        {
            "conversations-002.json": [_conversation("second")],
            "conversations-001.json": [_conversation("first")],
            "shared_conversations.json": [
                {
                    "id": "share-id",
                    "conversation_id": "first",
                    "title": "Link",
                    "is_anonymous": True,
                }
            ],
        },
    )

    plan = MemoryRestoreOrchestrator(
        _settings(source, tmp_path / "test_03"), tool_root=tmp_path / "repo"
    ).plan([export])

    assert plan.ok
    assert plan.chats[0]["canonical_conversation_members"] == [
        "conversations-001.json",
        "conversations-002.json",
    ]
    assert plan.chats[0]["shared_conversation_members"] == ["shared_conversations.json"]
    assert plan.chats[0]["plan"]["conversation_counters"] == {"new": 2}


def test_prepared_plan_is_invalidated_when_source_bytes_change(tmp_path: Path) -> None:
    source = tmp_path / "exports"
    source.mkdir()
    export = source / "chatGPT-export-2025.07.19.zip"
    _write_zip(export, {"conversations.json": [_conversation("first")]})
    target = tmp_path / "test_03"
    orchestrator = MemoryRestoreOrchestrator(
        _settings(source, target), tool_root=tmp_path / "repo"
    )
    plan = orchestrator.plan([export])
    _write_zip(export, {"conversations.json": [_conversation("changed")]})

    with pytest.raises(ValueError, match="source changed after plan"):
        orchestrator.run(
            [export],
            confirmation=DEVELOPER_CONFIRMATION,
            prepared_plan=plan,
        )
    assert not target.exists()


def test_explicit_source_order_is_preserved_and_duplicates_are_removed(tmp_path: Path) -> None:
    source = tmp_path / "exports"
    source.mkdir()
    older = source / "chatGPT-export-2025.07.18.zip"
    newer = source / "chatGPT-export-2025.07.19.zip"
    _write_zip(older, {"conversations.json": [_conversation("older")]})
    _write_zip(newer, {"conversations.json": [_conversation("newer")]})
    orchestrator = MemoryRestoreOrchestrator(
        _settings(source, tmp_path / "test_03"), tool_root=tmp_path / "repo"
    )

    plan = orchestrator.plan([newer, older, newer])

    assert plan.selected_sources == [newer.resolve(), older.resolve()]
    assert [Path(item["path"]) for item in plan.chats] == [newer.resolve(), older.resolve()]


def test_operator_tool_reports_v240205_and_orders_dates_not_sizes(tmp_path: Path) -> None:
    tool_path = Path(__file__).resolve().parents[1] / "tools" / "memory_rebuild.py"
    module_name = "memory_rebuild_v240205_test"
    spec = importlib.util.spec_from_file_location(module_name, tool_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)

    older = RestoreSource(tmp_path / "chatGPT-export-2025.07.18.zip", 999_999, ".zip")
    newer = RestoreSource(tmp_path / "chatGPT-export-2025.07.19.zip", 1, ".zip")

    assert module.TOOL_VERSION == "24.0.2.05"
    assert module._ordered_restore_sources([newer, older]) == [older, newer]


def test_operator_settings_show_effective_memory_boundaries(tmp_path: Path) -> None:
    tool_path = Path(__file__).resolve().parents[1] / "tools" / "memory_rebuild.py"
    module_name = "memory_rebuild_v240205_boundaries_test"
    spec = importlib.util.spec_from_file_location(module_name, tool_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)

    rows, details = module._memory_boundary_rows(MemoryRestoreSettings(candidate_limit=0))

    assert rows == [
        "Kandydaci doświadczeń: [OFF]",
        "Automatyczna akceptacja doświadczeń: [OFF — STAŁE]",
        "Automatyczna promocja L2: [OFF — STAŁE]",
        "Automatyczna promocja L3: [OFF — STAŁE]",
        "Analiza grafik i mediów: [OFF — NIEOBSŁUGIWANA]",
    ]
    assert len(details) == len(rows)
    assert all("ON" not in row for row in rows)

    enabled_rows, _ = module._memory_boundary_rows(MemoryRestoreSettings(candidate_limit=7))
    assert enabled_rows[0] == "Kandydaci doświadczeń: [ON — próbka 7]"
    assert enabled_rows[1:] == rows[1:]
