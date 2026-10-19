"""Regression tests for actual Memory Studio actions and private-memory isolation."""
from __future__ import annotations

from pathlib import Path
from collections.abc import Sequence
from typing import Any, cast
import tkinter as tk
from types import SimpleNamespace
import sys

import pytest

pytest.importorskip("tkinter")

from latka_jazn.core.runtime_root import workspace_runtime_path
from latka_jazn.tools.memory_rebuild_app import ui_desktop
from latka_jazn.tools.memory_rebuild_app.models import RebuildProject
from latka_jazn.tools.memory_rebuild_app.studio import StudioState
from latka_jazn.tools.memory_rebuild_app.project_store import ProjectStore
from latka_jazn.tools.memory_rebuild_app.studio_workflows import StudioWorkflows
from latka_jazn.tools.memory_rebuild_app.studio_write_safety import (
    require_isolated_database, require_isolated_staging_path,
)


def _project(tmp_path: Path) -> tuple[Path, RebuildProject]:
    project_root = tmp_path / "projects"
    target = tmp_path / "staging"
    project = RebuildProject.create("Synthetic", target)
    project.settings["unified_database_path"] = str(target / "memory" / "sqlite" / "memory_jazn.sqlite3")
    ProjectStore(project_root).create(project)
    return project_root, project


def test_project_is_bound_to_database_during_gui_initialization(monkeypatch, tmp_path: Path) -> None:
    project_root, project = _project(tmp_path)
    class FakeRoot:
        def __getattr__(self, name):
            return lambda *args, **kwargs: None

    monkeypatch.setattr(ui_desktop, "TkStudioDialogs", lambda root: SimpleNamespace())
    monkeypatch.setattr(ui_desktop.DesktopWorkspace, "_configure_theme", lambda self: None)
    monkeypatch.setattr(ui_desktop.DesktopWorkspace, "_layout", lambda self: None)
    monkeypatch.setattr(ui_desktop.DesktopWorkspace, "open_page", lambda self, page: None)
    app = ui_desktop.DesktopWorkspace(
        cast(tk.Tk, FakeRoot()), tool_root=tmp_path / "repo", project_root=project_root,
        project=project.project_id, settings_path=tmp_path / "settings.json",
        diagnostics=SimpleNamespace(),
    )
    assert app.state.database == Path(project.settings["unified_database_path"]).resolve()


def test_import_action_does_not_reenter_busy_executor(monkeypatch, tmp_path: Path) -> None:
    _, project = _project(tmp_path)
    source = tmp_path / "chat-export.json"
    source.write_text("{}", encoding="utf-8")
    calls = []
    class FakeMemoryDB:
        def __init__(self, path):
            calls.append(("db", Path(path)))
        def import_sources(self, paths, *, full_validation):
            calls.append(("import", tuple(paths), full_validation))
            return {"ok": True}

    monkeypatch.setattr(ui_desktop, "UnifiedMemoryDatabase", FakeMemoryDB)
    app = cast(Any, object.__new__(ui_desktop.DesktopWorkspace))
    app.tool_root = tmp_path / "repo"
    app.state = SimpleNamespace(database=Path(project.settings["unified_database_path"]))
    app.dialogs = SimpleNamespace(confirm=lambda *a: True, message=lambda *a: None)
    app._require_project = lambda: project
    app._busy = True  # Outer _execute already owns this action.
    app._execute = lambda *a, **kw: pytest.fail("Nested _execute would drop import")
    app._import_selected([source])
    assert ("import", (source,), True) in calls


def test_staging_guard_rejects_active_and_legacy_memory(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "repo"
    active_memory = workspace_runtime_path(root) / "memory"
    target = active_memory / "sqlite" / "memory_jazn.sqlite3"
    with pytest.raises(ValueError, match="Blokada zapisu"):
        require_isolated_database(target, tool_root=root, project_target=active_memory)
    with pytest.raises(ValueError, match="Blokada zapisu"):
        require_isolated_staging_path(root / "memory" / "sqlite" / "memory_jazn.sqlite3", tool_root=root)
    external = tmp_path / "another-volume" / "active"
    monkeypatch.setenv("JAZN_MEMORY_ROOT", str(external))
    with pytest.raises(ValueError, match="Blokada zapisu"):
        require_isolated_database(external / "sqlite" / "memory_jazn.sqlite3", tool_root=root)
    assert require_isolated_database(tmp_path / "staging" / "memory_jazn.sqlite3", tool_root=root) == (
        tmp_path / "staging" / "memory_jazn.sqlite3"
    )


def test_export_uses_project_final_output_setting(monkeypatch, tmp_path: Path) -> None:
    project_root, project = _project(tmp_path)
    output = tmp_path / "published"
    project.settings["final_output"] = str(output)
    ProjectStore(project_root).save(project)
    prompts = []
    exports = []
    class Dialogs:
        def choice(self, title: str, text: str, values: Sequence[tuple[Any, str]], *,
                   default: Any = None) -> Any:
            return None
        def checklist(self, title: str, text: str, values: Sequence[tuple[str, str]], *,
                      default_values: Sequence[str] = ()) -> list[str] | None:
            return None
        def input(self, title: str, text: str, default: str = "") -> str:
            prompts.append(default)
            return default
        def message(self, title: str, text: str) -> None:
            return None
        def confirm(self, title: str, text: str) -> bool:
            return False

    monkeypatch.setattr(
        "latka_jazn.tools.memory_rebuild_app.studio_workflows.export_final_memory",
        lambda db, destination, **kwargs: exports.append(destination) or {"ok": True},
    )
    state = StudioState(
        database=Path(project.settings["unified_database_path"]),
        project_root=project_root, project=project.project_id,
        tool_root=tmp_path / "repo", settings_path=tmp_path / "settings.json",
    )
    state.select_project(project.project_id)
    StudioWorkflows(state, Dialogs()).export()
    assert prompts == [str(output)]
    assert exports == [output]


def test_launcher_import_path_without_repository_cwd(tmp_path: Path, monkeypatch) -> None:
    from tools.jazn_memory_studio import resolve_working_root
    repository = tmp_path / "installed"
    pkg = repository / "latka_jazn"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("JAZN_ROOT", raising=False)
    try:
        assert resolve_working_root(repository) == repository.resolve()
        assert str(repository.resolve()) in sys.path
    finally:
        sys.path.remove(str(repository.resolve()))
