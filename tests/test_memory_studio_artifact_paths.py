"""Synthetic, isolated regression tests for project-owned Studio artifacts."""

from __future__ import annotations

from pathlib import Path

import pytest

from latka_jazn.tools.memory_rebuild_app import studio, ui_desktop
from latka_jazn.tools.memory_rebuild_app.models import RebuildProject, SourceSpec
from latka_jazn.tools.memory_rebuild_app.project_store import ProjectStore
from latka_jazn.tools.memory_rebuild_app.studio_artifact_paths import project_artifact_paths


def _project_state(tmp_path: Path) -> tuple[studio.StudioState, RebuildProject, Path]:
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    sources = tmp_path / "private_sources"
    sources.mkdir()
    source = sources / "conversations.json"
    source.write_text("[]", encoding="utf-8")
    project = RebuildProject.create(
        "Synthetic isolated project",
        tmp_path / "lab" / "work",
        source_directory=sources,
    )
    project.sources = [
        SourceSpec.create(
            source, role="chatgpt_export", truth_domain="conversation_event",
            pipeline="memory_rebuild", status="ready",
        )
    ]
    store = ProjectStore(tmp_path / "projects")
    store.create(project)
    state = studio.StudioState(
        database=tmp_path / "lab" / "work" / "memory" / "sqlite" / "memory_jazn.sqlite3",
        project_root=tmp_path / "projects",
        project=None,
        tool_root=checkout,
        settings_path=tmp_path / "settings.json",
    )
    state.select_project(project.project_id)
    return state, project, source


def test_project_artifact_directories_are_external_and_not_created_by_probe(tmp_path: Path) -> None:
    state, _, _ = _project_state(tmp_path)
    protocols, reports = state.private_artifact_paths()
    assert protocols == tmp_path / "lab" / "protocols"
    assert reports == tmp_path / "lab" / "reports"
    assert not protocols.exists()
    assert not reports.exists()


def test_resolved_artifact_path_refuses_checkout_and_private_sources(tmp_path: Path) -> None:
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    with pytest.raises(ValueError, match="repozytorium"):
        project_artifact_paths(target_root=checkout / "inside" / "work", tool_root=checkout)
    with pytest.raises(ValueError, match="pokrywać"):
        project_artifact_paths(
            target_root=tmp_path / "lab" / "work",
            tool_root=checkout,
            source_directory=tmp_path / "lab",
        )


def test_nonstandard_target_uses_nested_artifacts(tmp_path: Path) -> None:
    protocols, reports = project_artifact_paths(
        target_root=tmp_path / "target-alpha",
        tool_root=tmp_path / "checkout",
    )
    assert protocols == tmp_path / "target-alpha" / "_studio_artifacts" / "protocols"
    assert reports == tmp_path / "target-alpha" / "_studio_artifacts" / "reports"


def test_protocol_resume_and_test00_use_the_same_project_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    state, _, source = _project_state(tmp_path)
    captured = []

    class DummyService:
        def __init__(self, output_root, **kwargs):
            captured.append((Path(output_root), dict(kwargs)))
            self.engine = type("Engine", (), {"results": {}})()

        def run_step(self, profile, **kwargs):
            assert profile == "test00"
            assert kwargs["sources"] == [source.resolve()]
            return {"ok": True, "outcome": "PASSED"}

    class DummyDialogs(studio.TextDialogs):
        """Full DialogBackend surface with a non-interactive message sink."""

        def message(self, title: str, text: str) -> None:
            # Test00 output is not part of this artifact-path assertion.
            pass

    monkeypatch.setattr(studio, "MemoryRebuildApplicationService", DummyService)
    studio._run_test(state, DummyDialogs(), "test00")
    state.resume_step_run("synthetic-run")
    assert len(captured) == 2
    assert captured[0][0] == captured[1][0] == tmp_path / "lab" / "protocols"
    assert captured[1][1]["resume"] is True
    assert captured[1][1]["run_id"] == "synthetic-run"
    assert not (state.tool_root / "memory" / "rebuild_tests").exists()


def test_source_validation_gui_targets_private_reports(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    state, project, source = _project_state(tmp_path)
    destinations = []

    def fake_check(paths, *, report_dir):
        destinations.append(Path(report_dir))
        assert paths == [source.resolve()]
        return {
            "status": "PASSED",
            "file_count": 1,
            "counts": {},
            "total_size_bytes": 2,
            "report_paths": {},
        }

    class SilentGuiDialogs(ui_desktop.TkStudioDialogs):
        """Keep TkStudioDialogs typing without constructing a Tk window."""

        def __init__(self) -> None:
            pass

        def message(self, title: str, text: str) -> None:
            pass

    class StubDesktop(ui_desktop.DesktopWorkspace):
        """Real DesktopWorkspace subtype with only the dependencies under test."""

        def __init__(self) -> None:
            self.state = state
            self.dialogs = SilentGuiDialogs()

        def _require_project(self) -> RebuildProject:
            return project

    monkeypatch.setattr(ui_desktop, "check_memory_source_files", fake_check)
    ui_desktop.DesktopWorkspace._verify_source_files(StubDesktop())
    assert destinations == [tmp_path / "lab" / "reports" / "file_checks"]


def test_switching_projects_does_not_reuse_previous_protocol_chain(tmp_path: Path) -> None:
    state, project, _ = _project_state(tmp_path)
    other = RebuildProject.create("Other synthetic project", tmp_path / "other" / "work")
    ProjectStore(tmp_path / "projects").create(other)
    state.protocol_service = object()  # type: ignore[assignment]
    state.test_results["test00"] = {"ok": True}
    state.select_project(project.project_id)
    assert state.protocol_service is not None  # same project
    state.select_project(other.project_id)
    assert state.protocol_service is None
    assert state.test_results == {}
