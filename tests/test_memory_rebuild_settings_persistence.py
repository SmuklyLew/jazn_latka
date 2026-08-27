from __future__ import annotations

import json
from pathlib import Path

import pytest

from latka_jazn.tools.memory_rebuild_app.settings import (
    DEFAULT_SETTINGS_FILENAME,
    SETTINGS_SCHEMA,
    MemoryRebuildSettings,
    MemoryRebuildStudioPreferences,
    MemoryRebuildToolSettings,
    load_settings,
    load_tool_settings,
    resolve_settings_path,
    save_tool_settings,
)
from latka_jazn.tools.memory_rebuild_app.studio_v16316_settings import (
    PROJECT_LOCKED_SETTINGS,
    STUDIO_VERSION,
    StudioV16316State,
)
from latka_jazn.version import PACKAGE_VERSION_FULL


def _text(fragments) -> str:
    return "".join(str(text) for _style, text in fragments)


def test_default_tool_settings_are_created_as_full_structured_json(tmp_path: Path) -> None:
    path = tmp_path / DEFAULT_SETTINGS_FILENAME
    settings = load_tool_settings(path, tool_root=tmp_path, create=True)

    assert path.is_file()
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == SETTINGS_SCHEMA
    assert set(payload) == {"schema_version", "runtime", "studio"}
    assert set(payload["runtime"]) == set(MemoryRebuildSettings.__dataclass_fields__)
    assert set(payload["studio"]) == set(MemoryRebuildStudioPreferences.__dataclass_fields__)
    assert settings.runtime.require_fts5 is True
    assert settings.runtime.require_provenance is True
    assert settings.runtime.automatic_l2 is False
    assert settings.runtime.automatic_l3 is False
    assert settings.runtime.automatic_activation is False


def test_settings_round_trip_is_atomic_and_runtime_loader_stays_compatible(tmp_path: Path) -> None:
    path = tmp_path / DEFAULT_SETTINGS_FILENAME
    original = MemoryRebuildToolSettings(
        runtime=MemoryRebuildSettings(
            retrieval_limit=77,
            min_lexical_score=0.25,
            embeddings_enabled=True,
            embedding_model="local/test-embedding",
        ),
        studio=MemoryRebuildStudioPreferences(theme_name="latka-default"),
    )
    saved = save_tool_settings(original, path)

    assert saved == path.resolve()
    assert not path.with_name(path.name + ".tmp").exists()
    loaded = load_tool_settings(path)
    assert loaded == original
    assert load_settings(path) == original.runtime


def test_legacy_flat_runtime_settings_are_accepted_and_upgraded(tmp_path: Path) -> None:
    path = tmp_path / DEFAULT_SETTINGS_FILENAME
    path.write_text(
        json.dumps(
            {
                "retrieval_limit": 31,
                "min_lexical_score": 0.1,
                "embeddings_enabled": False,
            }
        ),
        encoding="utf-8",
    )

    loaded = load_tool_settings(path, create=True)

    assert loaded.runtime.retrieval_limit == 31
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == SETTINGS_SCHEMA
    assert payload["runtime"]["retrieval_limit"] == 31
    assert payload["studio"]["theme_name"]


def test_default_path_prefers_host_workspace_and_explicit_path_wins(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "workspace_runtime"
    tool_root = tmp_path / "tool"
    explicit = tmp_path / "custom.json"
    monkeypatch.delenv("JAZN_MEMORY_REBUILD_SETTINGS", raising=False)
    monkeypatch.setenv("JAZN_RUNTIME_WORKSPACE_DIR", str(workspace))

    assert resolve_settings_path(tool_root=tool_root) == (
        workspace / DEFAULT_SETTINGS_FILENAME
    ).resolve()
    assert resolve_settings_path(explicit, tool_root=tool_root) == explicit.resolve()


def test_environment_settings_path_beats_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_path = tmp_path / "env-settings.json"
    monkeypatch.setenv("JAZN_MEMORY_REBUILD_SETTINGS", str(env_path))
    monkeypatch.setenv("JAZN_RUNTIME_WORKSPACE_DIR", str(tmp_path / "workspace"))

    assert resolve_settings_path(tool_root=tmp_path / "tool") == env_path.resolve()


@pytest.mark.parametrize(
    ("changes", "pattern"),
    [
        ({"require_fts5": False}, "FTS5"),
        ({"require_provenance": False}, "Proweniencja"),
        ({"automatic_l2": True}, "automatyczne"),
        ({"automatic_l3": True}, "automatyczne"),
        ({"automatic_activation": True}, "automatyczne"),
    ],
)
def test_safety_invariants_cannot_be_enabled_or_disabled(changes: dict, pattern: str) -> None:
    with pytest.raises(ValueError, match=pattern):
        MemoryRebuildSettings(**changes)


def test_locked_runtime_fields_cannot_be_overridden_through_editor_contract() -> None:
    settings = MemoryRebuildSettings()

    with pytest.raises(ValueError, match="tylko do odczytu"):
        settings.with_overrides(require_provenance=False)


def test_unknown_structured_settings_fail_closed() -> None:
    with pytest.raises(ValueError, match="Nieznane sekcje"):
        MemoryRebuildToolSettings.from_mapping({"schema_version": SETTINGS_SCHEMA, "mystery": {}})


def test_v16316_studio_creates_settings_and_marks_editable_vs_read_only(tmp_path: Path) -> None:
    settings_path = tmp_path / DEFAULT_SETTINGS_FILENAME
    state = StudioV16316State(
        database=tmp_path / "memory_jazn.sqlite3",
        project_root=tmp_path / "projects",
        project=None,
        tool_root=tmp_path,
        settings_path=settings_path,
    )

    assert STUDIO_VERSION == "memory-rebuild-studio/v16.3.16"
    assert STUDIO_VERSION in _text(state.header_fragments())
    assert settings_path.is_file()
    assert state.settings_file == settings_path.resolve()

    state.set_page("settings")
    rendered = _text(state.content_fragments())
    assert "[EDYTOWALNE" in rendered
    assert "[READ-ONLY" in rendered
    assert str(settings_path.resolve()) in rendered
    for key in MemoryRebuildSettings.__dataclass_fields__:
        assert f"{key}:" in rendered
    for key in PROJECT_LOCKED_SETTINGS:
        assert key in rendered


def test_v16316_studio_runtime_changes_and_theme_persist(tmp_path: Path) -> None:
    settings_path = tmp_path / DEFAULT_SETTINGS_FILENAME
    state = StudioV16316State(
        database=tmp_path / "memory_jazn.sqlite3",
        project_root=tmp_path / "projects",
        project=None,
        tool_root=tmp_path,
        settings_path=settings_path,
    )

    state.set_runtime(state.runtime_settings.with_overrides(retrieval_limit=41))
    state.set_theme("latka-default")

    reloaded = load_tool_settings(settings_path)
    assert reloaded.runtime.retrieval_limit == 41
    assert reloaded.studio.theme_name == "latka-default"


def test_release_version_tracks_v16316_settings_studio() -> None:
    assert PACKAGE_VERSION_FULL == "16.3.16-memory-rebuild-settings-studio"
