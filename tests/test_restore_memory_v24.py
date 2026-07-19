from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "restore_memory.py"


def load_tool():
    spec = importlib.util.spec_from_file_location("restore_memory_v24_under_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_restore_memory_v24_contract() -> None:
    tool = load_tool()
    assert tool.TOOL_VERSION == "24.0.1"
    assert tool.TOOL_SCHEMA == "jazn_memory_restore_tool/v24"
    assert tool.default_config_path().resolve() != (ROOT / "tools" / "restore_memory_settings.json").resolve()


def test_configuration_roundtrip_keeps_sources_outside_repo(tmp_path: Path) -> None:
    tool = load_tool()
    source = tmp_path / "chatGPT-export.zip"
    source.write_bytes(b"PK\x03\x04fixture")
    settings = tool.MemoryRestoreSettings(
        source_directory=str(tmp_path),
        target_root=str(tmp_path / "test_03"),
        mode="developer",
        baseline_roots=[str(tmp_path / "test_01"), str(tmp_path / "test_02")],
    )
    config = tmp_path / "restore_memory_test_03.json"
    state = tool.ToolState(settings, [source], ui_mode="text", config_path=config)
    saved = tool.save_state(state)
    loaded = tool.load_state(saved)
    assert loaded.settings.mode == "developer"
    assert loaded.settings.baseline_roots == [
        str((tmp_path / "test_01").resolve()),
        str((tmp_path / "test_02").resolve()),
    ]
    assert loaded.selected_paths == [source.resolve()]
    assert json.loads(saved.read_text(encoding="utf-8"))["tool_version"] == "24.0.1"


def test_configuration_refuses_repository_path() -> None:
    tool = load_tool()
    state = tool.ToolState(tool.default_settings(), ui_mode="text")
    with pytest.raises(tool.RestoreToolError, match="poza repozytorium"):
        tool.save_state(state, ROOT / "tools" / "restore_memory_settings.json")


def test_safe_defaults_do_not_promote_memory() -> None:
    tool = load_tool()
    settings = tool.default_settings()
    assert settings.create_backup is True
    assert settings.verify_after_each is True
    assert settings.full_validation is True
    assert settings.continue_on_error is False
    assert settings.reclassify_journal_dry_run is True
    assert settings.apply_reclassification is False
    assert settings.analyse_topics is False
    assert settings.force_topics is False
    assert settings.candidate_limit == 0


def test_right_mouse_event_contract_when_prompt_toolkit_available() -> None:
    tool = load_tool()
    if not tool.HAS_PROMPT_TOOLKIT:
        pytest.skip("prompt_toolkit is optional")
    from prompt_toolkit.data_structures import Point
    from prompt_toolkit.mouse_events import MouseButton, MouseEvent, MouseEventType

    event = MouseEvent(
        position=Point(x=0, y=0),
        event_type=MouseEventType.MOUSE_UP,
        button=MouseButton.RIGHT,
        modifiers=frozenset(),
    )
    assert tool._is_right_up(event) is True
    assert tool._is_left_up(event) is False


def test_launcher_does_not_depend_on_legacy_tools() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    forbidden = (
        "tools.memory_import_to_db",
        "tools.memory_import_anywhere",
        "tools.memory_import_ui",
        "tools.memory_import_snapshot",
        "tools.memory_migrate_legacy_v151",
    )
    for name in forbidden:
        assert name not in source
    assert "latka_jazn.tools.memory_restore" in source


def test_plan_report_save_writes_readable_and_exact_payload(tmp_path: Path) -> None:
    tool = load_tool()
    settings = tool.MemoryRestoreSettings(
        source_directory=str(tmp_path),
        target_root=str(tmp_path / "jazn_memory_test_03"),
        mode="developer",
    )
    state = tool.ToolState(settings=settings, ui_mode="text")
    plan = tool.MemoryRestorePlan(
        settings=settings,
        selected_sources=[tmp_path / "one.zip"],
        chats=[{"path": str(tmp_path / "one.zip")}],
        journals=[],
        rejected=[],
        target_preflight={"ok": True, "blocking_errors": []},
        current_status={},
    )
    text_path, json_path = tool.save_plan_report(state, plan, "PLAN TEST")
    assert text_path.parent == tmp_path / "restore_memory_plans"
    assert text_path.read_text(encoding="utf-8") == "PLAN TEST\n"
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["ok"] is True
    assert payload["chat_source_count"] == 1
    assert not text_path.name.endswith(".tmp")
    assert not json_path.name.endswith(".tmp")


def test_cursor_report_binds_copy_and_save_shortcuts() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert '@keys.add("c-c", eager=True)' in source
    assert '@keys.add("c-s", eager=True)' in source
    assert "copy_system_clipboard(text)" in source
    assert "save_callback=lambda: save_plan_report(state, plan, text)" in source
