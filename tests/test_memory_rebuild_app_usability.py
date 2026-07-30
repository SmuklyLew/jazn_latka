from __future__ import annotations

from pathlib import Path

from latka_jazn.tools.memory_rebuild_app.models import RebuildProject, SourceSpec
from latka_jazn.tools.memory_rebuild_app.presentation import (
    format_preflight,
    format_source,
    source_title,
)
from latka_jazn.tools.memory_rebuild_app.source_browser import (
    discover_source_files,
    format_discovered_files,
)
from latka_jazn.tools.memory_rebuild_app.tui import MemoryRebuildStudio


def test_source_discovery_includes_dot_prefixed_old_folder(tmp_path: Path) -> None:
    (tmp_path / "chat-export.zip").write_bytes(b"zip")
    old = tmp_path / ".BardzoStareCos"
    old.mkdir()
    (old / "journal.jsonl").write_text('{"entry": 1}\n', encoding="utf-8")
    (old / "journal.jsonl.sha256").write_text("digest", encoding="utf-8")

    discovered = discover_source_files(tmp_path, recursive=True)
    relative = [str(path.relative_to(tmp_path)) for path in discovered]

    assert relative == [".BardzoStareCos/journal.jsonl", "chat-export.zip"]
    preview = format_discovered_files(tmp_path, discovered)
    assert "[.BardzoStareCos]" in preview
    assert "journal.jsonl" in preview
    assert "journal.jsonl.sha256" not in preview


def test_preflight_summary_explains_how_to_fix_folder_added_as_source(tmp_path: Path) -> None:
    report = {
        "ok": False,
        "errors": ["enabled_sources_blocked", "no_memory_rebuild_sources"],
        "enabled_source_count": 1,
        "memory_rebuild_source_count": 0,
        "catalog_only_source_count": 1,
        "html_control_source_count": 0,
        "target_root": str(tmp_path / "target"),
        "missing_sources": [],
        "blocked_sources": [
            {
                "path": str(tmp_path / "memory_to_restore"),
                "warnings": ["blocking:source_not_file"],
            }
        ],
    }

    text = format_preflight(report)

    assert "GOTOWOŚĆ PROJEKTU: WYMAGA POPRAWY" in text
    assert "Podana ścieżka jest folderem" in text
    assert "Przeskanuj folder" in text
    assert "no_memory_rebuild_sources" not in text


def test_source_list_and_preview_are_human_readable(tmp_path: Path) -> None:
    path = tmp_path / "journal_from_sqlite.jsonl"
    path.write_text('{"id": 1}\n', encoding="utf-8")
    source = SourceSpec.create(
        path,
        role="journal",
        truth_domain="source_recorded",
        pipeline="memory_rebuild",
        approved=True,
        size_bytes=path.stat().st_size,
        status="ready",
        metadata={"jsonl": {"sample_valid_json": 1, "sample_invalid_json": 0}},
    )
    source.order = 1

    title = source_title(source)
    preview = format_source(source)

    assert "Dziennik" in title
    assert "journal_from_sqlite.jsonl" in title
    assert "Wejdzie do odbudowy pamięci" in preview
    assert "poprawne rekordy: 1" in preview
    assert "source_recorded" not in preview


def test_project_stage_starts_with_source_guidance(tmp_path: Path) -> None:
    project = RebuildProject.create("Test", tmp_path / "target")
    studio = MemoryRebuildStudio.__new__(MemoryRebuildStudio)
    studio.project = project

    assert "dodaj lub przeskanuj źródła" in studio.project_stage()
