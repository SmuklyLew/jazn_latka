from __future__ import annotations

from pathlib import Path

import pytest

from latka_jazn.tools.memory_rebuild_app.models import DEFAULT_SETTINGS
from latka_jazn.tools.memory_rebuild_app.settings import MemoryRebuildSettings
from latka_jazn.tools.memory_rebuild_app.studio_p0 import (
    PAGE_IDS,
    SETTINGS_ITEMS,
    STUDIO_P0_VERSION,
    StudioState,
    TEST_PRESENTATIONS,
)
from latka_jazn.tools.memory_rebuild_app.test_profiles import PROFILE_NAMES
from latka_jazn.tools.memory_rebuild_app.themes import (
    DEFAULT_STUDIO_THEME_NAME,
    TERMINAL_STUDIO_THEME,
    get_theme,
    prompt_toolkit_style,
)
from latka_jazn.version import PACKAGE_VERSION_FULL


def _text(fragments) -> str:
    return "".join(str(text) for _style, text in fragments)


def test_p0_studio_has_three_operator_pages() -> None:
    assert PAGE_IDS == ("tests", "design", "settings")
    assert STUDIO_P0_VERSION == "memory-rebuild-studio/v16.3.13"


def test_p0_test_page_tracks_canonical_test_profiles() -> None:
    assert tuple(item.profile for item in TEST_PRESENTATIONS) == PROFILE_NAMES
    test04 = next(item for item in TEST_PRESENTATIONS if item.profile == "test04")
    assert any("reconciliation" in check for check in test04.checks)
    assert any("recall" in check for check in test04.checks)
    assert any("HTML" in check for check in test04.checks)
    final = next(item for item in TEST_PRESENTATIONS if item.profile == "final")
    assert any("L3" in check for check in final.checks)


def test_settings_page_exposes_all_project_and_runtime_settings(tmp_path: Path) -> None:
    state = StudioState(
        database=tmp_path / "memory_jazn.sqlite3",
        project_root=tmp_path / "projects",
        project=None,
        tool_root=tmp_path,
    )
    state.set_page("settings")
    assert SETTINGS_ITEMS[0].key == "all"
    rendered = _text(state.content_fragments())
    for key in DEFAULT_SETTINGS:
        assert f"{key}:" in rendered
    for key in MemoryRebuildSettings.__dataclass_fields__:
        assert f"{key}:" in rendered


def test_terminal_theme_is_default_and_prompt_toolkit_style_is_valid() -> None:
    pytest.importorskip("prompt_toolkit")
    assert DEFAULT_STUDIO_THEME_NAME == "latka-terminal"
    assert get_theme().name == TERMINAL_STUDIO_THEME.name
    style = prompt_toolkit_style(TERMINAL_STUDIO_THEME)
    assert style is not None
    assert TERMINAL_STUDIO_THEME.border == "#F29A63"
    assert TERMINAL_STUDIO_THEME.accent == "#B58AF1"


def test_p0_layout_can_be_composed_without_running_terminal(tmp_path: Path) -> None:
    pytest.importorskip("prompt_toolkit")
    from latka_jazn.tools.memory_rebuild_app.layout import build_studio_layout

    state = StudioState(
        database=tmp_path / "memory_jazn.sqlite3",
        project_root=None,
        project=None,
        tool_root=tmp_path,
    )
    layout = build_studio_layout(state)
    assert layout.container is not None


def test_release_version_tracks_v16313_p0_studio() -> None:
    assert PACKAGE_VERSION_FULL == "16.3.13-memory-rebuild-p0-studio"
