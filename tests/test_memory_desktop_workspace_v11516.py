"""Native desktop memory Studio: headless operator contract regressions."""
from __future__ import annotations
from pathlib import Path
import pytest

pytest.importorskip("tkinter")

from latka_jazn.tools.memory_rebuild_app import ui_window
from latka_jazn.tools.memory_rebuild_app.config import APP_VERSION
from latka_jazn.tools.memory_rebuild_app.models import RebuildProject
from latka_jazn.tools.memory_rebuild_app.ui_desktop import (
    PAGES, PATH_FIELDS, project_path_values, proposed_path_changes,
)


def test_window_routes_to_native_canonical_workspace(monkeypatch, tmp_path: Path) -> None:
    import latka_jazn.tools.memory_rebuild_app.ui_desktop as desktop
    calls = {}
    monkeypatch.setattr(desktop, "run_desktop", lambda **kwargs: calls.update(kwargs) or 0)
    assert ui_window.run_window(tool_root=tmp_path, diagnostics=object(),
        project_root=tmp_path / "projects", project="project-1",
        settings_path=tmp_path / "settings.json") == 0
    assert calls["tool_root"] == tmp_path
    assert calls["project"] == "project-1"
    assert calls["settings_path"] == tmp_path / "settings.json"
    assert APP_VERSION == "3.1.0"


def test_all_major_memory_operator_functions_have_pages() -> None:
    ids = [key for key, title, help_text in PAGES]
    assert len(ids) == len(set(ids))
    assert {"home", "projects", "paths", "database", "import", "affect",
            "candidates", "tests", "rebuild", "export", "settings",
            "diagnostics"}.issubset(ids)
    keys = {key for key, *_ in PATH_FIELDS}
    assert {"source_directory", "target_root", "database", "test04_benchmark",
            "test04_acceptance_report", "restart_continuity_report",
            "final_output"}.issubset(keys)


def test_path_contract_maps_project_without_writing_files(tmp_path: Path) -> None:
    project = RebuildProject.create("Synthetic", tmp_path / "staging",
                                    source_directory=tmp_path / "sources")
    project.settings["test04_benchmark"] = str(tmp_path / "benchmark.json")
    db = tmp_path / "staging" / "memory_jazn.sqlite3"
    values = project_path_values(project, db)
    assert values["database"] == str(db)
    assert values["test04_benchmark"] == str(tmp_path / "benchmark.json")
    assert proposed_path_changes(values)["target_root"] == str(tmp_path / "staging")
    assert not (tmp_path / "staging").exists()


@pytest.mark.parametrize(("source", "staging"), [
    ("/tmp/sources", "/tmp/sources"),
    ("/tmp/sources", "/tmp/sources/staging"),
    ("/tmp/sources/data", "/tmp/sources"),
])
def test_source_and_staging_must_not_overlap(source: str, staging: str) -> None:
    with pytest.raises(ValueError, match="rozdzielone"):
        proposed_path_changes({"source_directory": source, "target_root": staging,
                               "database": "/tmp/output/memory_jazn.sqlite3"})


def test_canonical_paths_cannot_be_blank() -> None:
    with pytest.raises(ValueError, match="target_root"):
        proposed_path_changes({"target_root": "", "database": "/tmp/db.sqlite3"})
    with pytest.raises(ValueError, match="database"):
        proposed_path_changes({"target_root": "/tmp/staging", "database": ""})
