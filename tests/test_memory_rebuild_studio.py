from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from latka_jazn.tools.memory_rebuild_app import studio, studio_workflows, tui_v24
from latka_jazn.tools.memory_rebuild_app.models import DEFAULT_SETTINGS
from latka_jazn.tools.memory_rebuild_app.settings import MemoryRebuildSettings
from latka_jazn.tools.memory_rebuild_app.studio import (
    DESIGN_ITEMS,
    PAGE_IDS,
    SETTINGS_ITEMS,
    STUDIO_VERSION,
    StudioState,
)
from latka_jazn.tools.memory_rebuild_app.test_spec import TEST_PROTOCOL_ORDER
from latka_jazn.tools.memory_rebuild_app.themes import (
    DEFAULT_STUDIO_THEME_NAME,
    TERMINAL_STUDIO_THEME,
    get_theme,
    prompt_toolkit_style,
)
from latka_jazn.version import PACKAGE_VERSION_FULL


RETIRED_UI_MODULES = (
    "studio_p0.py",
    "studio_v16314.py",
    "studio_v16316_settings.py",
    "tui.py",
    "tui_candidates.py",
    "tui_common.py",
    "tui_export.py",
    "tui_import.py",
    "tui_paths.py",
    "tui_tests.py",
)


def _text(fragments) -> str:
    return "".join(str(text) for _style, text in fragments)


def _imported_modules(module) -> set[str]:
    tree = ast.parse(inspect.getsource(module))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            prefix = "." * node.level
            imported.add(prefix + str(node.module or ""))
    return imported


def test_studio_has_one_canonical_three_page_shell(tmp_path: Path) -> None:
    state = StudioState(
        database=tmp_path / "memory_jazn.sqlite3",
        project_root=tmp_path / "projects",
        project=None,
        tool_root=tmp_path,
        settings_path=tmp_path / "memory_rebuild_settings.json",
    )

    assert PAGE_IDS == ("tests", "design", "settings")
    assert STUDIO_VERSION == "memory-rebuild-studio/v16.3.17"
    assert STUDIO_VERSION in _text(state.header_fragments())

    state.set_page("tests")
    assert tuple(item.key for item in state.items()) == TEST_PROTOCOL_ORDER

    state.set_page("design")
    keys = tuple(item.key for item in state.items())
    assert keys == tuple(item.key for item in DESIGN_ITEMS)
    assert "rebuild" in keys
    assert "recall" in keys

    state.set_page("settings")
    assert tuple(item.key for item in state.items()) == tuple(item.key for item in SETTINGS_ITEMS)


def test_projecting_actions_do_not_import_or_launch_retired_ui_layers() -> None:
    modules = (studio, studio_workflows, tui_v24)
    imported = set().union(*(_imported_modules(module) for module in modules))
    banned = {
        ".tui",
        ".tui_common",
        ".tui_import",
        ".tui_candidates",
        ".tui_export",
        ".tui_paths",
        ".studio_p0",
        ".studio_v16314",
        ".studio_v16316_settings",
    }

    assert not (imported & banned)
    source = "\n".join(inspect.getsource(module) for module in modules)
    assert "run_project_studio(" not in source
    assert "source_import_menu(" not in source
    assert "candidate_menu(" not in source
    assert "final_export_menu(" not in source


def test_retired_ui_implementations_are_not_shipped() -> None:
    package_dir = Path(studio.__file__).resolve().parent
    present = [name for name in RETIRED_UI_MODULES if (package_dir / name).exists()]
    assert present == []
    assert (package_dir / "tui_v24.py").is_file()


def test_studio_test_and_recall_surfaces_use_shared_protocol_specs(tmp_path: Path) -> None:
    state = StudioState(
        database=tmp_path / "memory_jazn.sqlite3",
        project_root=tmp_path / "projects",
        project=None,
        tool_root=tmp_path,
        settings_path=tmp_path / "memory_rebuild_settings.json",
    )
    state.set_page("tests")
    rendered = _text(state.content_fragments())
    for section in (
        "CEL",
        "WEJŚCIA",
        "GOTOWOŚĆ",
        "FAZY",
        "KONTROLE",
        "WYNIK",
        "WYJŚCIA",
        "GRANICA PRAWDY",
    ):
        assert section in rendered
    assert "Source Fidelity" in rendered

    state.set_page("design")
    state.selected["design"] = len(state.items()) - 1
    recall = _text(state.content_fragments())
    assert "FTS5" in recall
    assert "ZABLOKOWANE" in recall


def test_settings_page_exposes_project_and_runtime_settings(tmp_path: Path) -> None:
    state = StudioState(
        database=tmp_path / "memory_jazn.sqlite3",
        project_root=tmp_path / "projects",
        project=None,
        tool_root=tmp_path,
        settings_path=tmp_path / "memory_rebuild_settings.json",
    )
    state.set_page("settings")
    rendered = _text(state.content_fragments())

    for key in DEFAULT_SETTINGS:
        assert f"{key}:" in rendered
    for key in MemoryRebuildSettings.__dataclass_fields__:
        assert f"{key}:" in rendered
    assert "model_training: NIE" in rendered


def test_terminal_theme_is_shared_by_shell_and_dialog_contract() -> None:
    pytest.importorskip("prompt_toolkit")
    assert DEFAULT_STUDIO_THEME_NAME == "latka-terminal"
    assert get_theme().name == TERMINAL_STUDIO_THEME.name
    assert prompt_toolkit_style(TERMINAL_STUDIO_THEME) is not None


def test_canonical_layout_composes_without_running_terminal(tmp_path: Path) -> None:
    pytest.importorskip("prompt_toolkit")
    from latka_jazn.tools.memory_rebuild_app.layout import build_studio_layout

    state = StudioState(
        database=tmp_path / "memory_jazn.sqlite3",
        project_root=None,
        project=None,
        tool_root=tmp_path,
        settings_path=tmp_path / "memory_rebuild_settings.json",
    )
    layout = build_studio_layout(state)
    assert layout.container is not None


def test_release_version_tracks_v16319_unified_studio_ci_fix() -> None:
    assert PACKAGE_VERSION_FULL == "16.3.19-memory-rebuild-unified-studio-ci-fix"
