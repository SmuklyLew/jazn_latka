"""Source picker and new-project path contracts without private user data."""
from __future__ import annotations

from pathlib import Path

import pytest

from latka_jazn.tools.memory_rebuild_app.canonical_rebuild import canonical_database_path
from latka_jazn.tools.memory_rebuild_app.models import RebuildProject, SourceSpec
from latka_jazn.tools.memory_rebuild_app.ui_desktop import (
    proposed_path_changes,
    suggested_database_after_target_change,
)


def test_change_of_staging_rebases_only_untouched_default_database(tmp_path: Path) -> None:
    first = tmp_path / "studio-repo" / "memory"
    second = tmp_path / "safe-project-outside-repo"
    previous_default = canonical_database_path(first)
    assert suggested_database_after_target_change(
        first, second, previous_default,
    ) == canonical_database_path(second)
    assert canonical_database_path(second) != previous_default


def test_custom_or_existing_database_is_never_silently_relocated(tmp_path: Path) -> None:
    old = tmp_path / "old-target"
    new = tmp_path / "new-target"
    custom = tmp_path / "another-safe-location" / "memory_jazn.sqlite3"
    assert suggested_database_after_target_change(old, new, custom) == custom.resolve()
    existing = canonical_database_path(old)
    existing.parent.mkdir(parents=True)
    existing.write_bytes(b"synthetic - not a database")
    assert suggested_database_after_target_change(old, new, existing) == existing.resolve()
    assert existing.read_bytes() == b"synthetic - not a database"


def test_target_and_source_must_not_overlap(tmp_path: Path) -> None:
    sources = tmp_path / "sources"
    output = sources / "staging"
    with pytest.raises(ValueError, match="muszą być rozdzielone"):
        proposed_path_changes({
            "source_directory": str(sources),
            "target_root": str(output),
            "database": str(canonical_database_path(output)),
        })


def test_one_project_registers_sources_from_separate_directories(tmp_path: Path) -> None:
    project = RebuildProject.create(
        "Synthetic project", tmp_path / "outputs",
        source_directory=tmp_path / "first-directory",
    )
    first = tmp_path / "first-directory" / "chat.json"
    second = tmp_path / "second-directory" / "older" / "journal.json"
    project.add_source(SourceSpec.create(first))
    project.add_source(SourceSpec.create(second))
    project.add_source(SourceSpec.create(first))
    assert len(project.sources) == 2
    assert {Path(item.path) for item in project.sources} == {
        first.resolve(), second.resolve(),
    }
    # A saved starting directory is not a restriction on the actual sources.
    assert project.source_directory == str((tmp_path / "first-directory").resolve())
