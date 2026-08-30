from __future__ import annotations

import re
from pathlib import Path

import pytest

from latka_jazn.tools.memory_rebuild_app.config import TOOL_RELEASE_LABEL, TOOL_REVISION
from latka_jazn.tools.memory_rebuild_app.models import DEFAULT_SETTINGS
from latka_jazn.tools.memory_rebuild_app.settings import MemoryRebuildSettings
from latka_jazn.tools.memory_rebuild_app.studio import (
    PAGE_IDS,
    SETTINGS_ITEMS,
    STUDIO_VERSION,
    StudioState,
)
from latka_jazn.tools.memory_rebuild_app.test_profiles import PROFILE_NAMES
from latka_jazn.tools.memory_rebuild_app.test_spec import TEST_PROTOCOL_ORDER, get_test_spec
from latka_jazn.tools.memory_rebuild_app.themes import (
    DEFAULT_STUDIO_THEME_NAME,
    TERMINAL_STUDIO_THEME,
    get_theme,
    prompt_toolkit_style,
)
from latka_jazn.version import PACKAGE_VERSION_FULL


def _text(fragments) -> str:
    return "".join(str(text) for _style, text in fragments)


def _state(tmp_path: Path) -> StudioState:
    return StudioState(
        database=tmp_path / "memory_jazn.sqlite3",
        project_root=tmp_path / "projects",
        project=None,
        tool_root=tmp_path,
        settings_path=tmp_path / "memory_rebuild_settings.json",
    )


def _numeric_release_prefix(value: str) -> tuple[int, ...]:
    match = re.match(r"^(\d+(?:\.\d+)*)", value)
    assert match is not None, f"release version has no numeric prefix: {value!r}"
    return tuple(int(part) for part in match.group(1).split("."))


def test_retired_p0_contract_is_owned_by_one_canonical_three_page_studio(tmp_path: Path) -> None:
    state = _state(tmp_path)
    assert PAGE_IDS == ("tests", "design", "settings")
    assert STUDIO_VERSION == "memory-rebuild-studio/v16.3.20"
    assert STUDIO_VERSION in _text(state.header_fragments())


def test_shared_protocol_preserves_validators_and_source_union_acceptance_contracts() -> None:
    assert TEST_PROTOCOL_ORDER == ("test00", *PROFILE_NAMES)

    test00 = get_test_spec("test00")
    assert any("source-set union" in item.casefold() for item in test00.phases)
    assert any("kolejność importu" in item.casefold() for item in test00.checks)
    assert any("branch_union" in item.casefold() for item in test00.checks)

    test03 = get_test_spec("test03")
    assert any("reconciliation" in item.casefold() for item in test03.phases)
    assert any("html" in item.casefold() for item in test03.phases)
    assert any("manual html" in item.casefold() for item in test03.checks)
    assert any("odwrócon" in item.casefold() for item in test03.phases)

    test04 = get_test_spec("test04")
    assert any("reconciliation" in item.casefold() for item in test04.phases)
    assert any("recall" in item.casefold() for item in test04.phases)
    assert any("credential" in item.casefold() for item in test04.checks)
    assert any("abstention" in item.casefold() for item in test04.checks)

    final = get_test_spec("final")
    assert any("promotion ledger" in item.casefold() for item in final.checks)
    assert any("backup api" in item.casefold() for item in final.phases)
    assert any("wal" in item.casefold() for item in final.checks)
    assert any("nie aktyw" in item.casefold() for item in final.truth_boundary)


def test_canonical_studio_uses_shared_test00_to_final_protocol_specs(tmp_path: Path) -> None:
    state = _state(tmp_path)
    state.set_page("tests")
    assert tuple(item.key for item in state.items()) == TEST_PROTOCOL_ORDER
    rendered = _text(state.content_fragments())
    for section in (
        "CEL",
        "WEJŚCIA",
        "GOTOWOŚĆ",
        "FAZY",
        "KONTROLE",
        "WYNIK",
        "DOWODY",
        "WYJŚCIA",
        "GRANICA PRAWDY",
    ):
        assert section in rendered
    assert "Source Fidelity" in rendered
    assert "brak — protokół nie był uruchamiany" in rendered

    state.set_page("design")
    state.selected["design"] = len(state.items()) - 1
    recall = _text(state.content_fragments())
    assert "FTS5" in recall
    assert "Recall@k" in recall
    assert "ZABLOKOWANE" in recall


def test_settings_page_exposes_all_project_and_runtime_settings(tmp_path: Path) -> None:
    state = _state(tmp_path)
    state.set_page("settings")
    assert SETTINGS_ITEMS[0].key == "all"
    rendered = _text(state.content_fragments())
    for key in DEFAULT_SETTINGS:
        assert f"{key}:" in rendered
    for key in MemoryRebuildSettings.__dataclass_fields__:
        assert f"{key}:" in rendered
    assert "baseline: fts5-bm25/v1" in rendered
    assert "model_training: NIE" in rendered
    assert "READ-ONLY / ZABLOKOWANE" in rendered


def test_terminal_theme_is_default_and_prompt_toolkit_style_is_valid() -> None:
    pytest.importorskip("prompt_toolkit")
    assert DEFAULT_STUDIO_THEME_NAME == "latka-terminal"
    assert get_theme().name == TERMINAL_STUDIO_THEME.name
    style = prompt_toolkit_style(TERMINAL_STUDIO_THEME)
    assert style is not None
    assert TERMINAL_STUDIO_THEME.border == "#F29A63"
    assert TERMINAL_STUDIO_THEME.accent == "#B58AF1"


def test_canonical_layout_can_be_composed_without_running_terminal(tmp_path: Path) -> None:
    pytest.importorskip("prompt_toolkit")
    from latka_jazn.tools.memory_rebuild_app.layout import build_studio_layout

    layout = build_studio_layout(_state(tmp_path))
    assert layout.container is not None


def test_memory_rebuild_revision_and_package_version_are_monotonic() -> None:
    assert TOOL_REVISION == "15.3.23.01"
    assert TOOL_RELEASE_LABEL == "15.3.23.01 - Poprawione narzędzie odbudowy pamięci"
    assert _numeric_release_prefix(PACKAGE_VERSION_FULL) >= (16, 3, 25, 3)
