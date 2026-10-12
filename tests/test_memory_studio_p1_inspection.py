from __future__ import annotations

from pathlib import Path
import sqlite3
import pytest

from latka_jazn.tools.memory_rebuild_app.models import RebuildProject, SourceSpec
from latka_jazn.tools.memory_rebuild_app.p1_memory_inspection import (
    SCHEMA, inspect_memory_layout,
)


def fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, RebuildProject]:
    root = tmp_path / "system"
    root.mkdir()
    monkeypatch.setenv("JAZN_RUNTIME_WORKSPACE_DIR", str(tmp_path / "operational"))
    monkeypatch.setenv("JAZN_MEMORY_ROOT", str(tmp_path / "private_memory"))
    return root, RebuildProject.create("synthetic", tmp_path / "rebuild")


def test_missing_inspection_does_not_create_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, project = fixture(tmp_path, monkeypatch)
    before = sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*"))
    report = inspect_memory_layout(project, system_root=root)
    after = sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*"))
    assert report["schema"] == SCHEMA
    assert report["roles"]["target"]["status"] == "missing"
    assert report["roles"]["staging"]["status"] == "missing"
    assert report["roles"]["host_selected_memory"]["active_daemon_verified"] is False
    assert report["readiness"]["activation_ready"] is False
    assert report["readiness"]["publishing_authorized"] is False
    assert before == after


def test_only_source_file_metadata_is_observed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, project = fixture(tmp_path, monkeypatch)
    source = tmp_path / "private-source.json"
    source.write_text("PRIVATE_SYNTHETIC_PAYLOAD", encoding="utf-8")
    project.sources = [SourceSpec.create(source), SourceSpec.create(tmp_path / "absent.json")]
    report = inspect_memory_layout(project, system_root=root)
    assert report["roles"]["source"]["present"] == 1
    assert report["roles"]["source"]["missing"] == 1
    assert report["private_content_read"] is False
    assert "PRIVATE_SYNTHETIC_PAYLOAD" not in str(report)
    assert str(tmp_path) not in str(report)


def test_foreign_sqlite_is_not_declared_native(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, project = fixture(tmp_path, monkeypatch)
    db = tmp_path / "rebuild/memory/sqlite/memory_jazn.sqlite3"
    db.parent.mkdir(parents=True)
    with sqlite3.connect(db) as con:
        con.execute("CREATE TABLE foreign_table(id INTEGER)")
    before = db.read_bytes()
    result = inspect_memory_layout(project, system_root=root)
    assert result["roles"]["target"]["exists"] is True
    assert result["roles"]["target"]["schema_compatible"] is False
    assert result["readiness"]["activation_ready"] is False
    assert db.read_bytes() == before
    assert sorted(p.name for p in db.parent.iterdir()) == [db.name]


def test_single_staging_candidate_cannot_publish(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, project = fixture(tmp_path, monkeypatch)
    db = tmp_path / "rebuild/memory/.rebuild_staging/run1/sqlite/memory_jazn.sqlite3"
    db.parent.mkdir(parents=True)
    sqlite3.connect(db).close()
    report = inspect_memory_layout(project, system_root=root)
    assert report["roles"]["staging"]["status"] == "candidate_inspected"
    assert report["roles"]["staging"]["published"] is False
    assert report["comparison"]["staging_promoted"] is False


def test_ambiguous_staging_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, project = fixture(tmp_path, monkeypatch)
    for name in ("run1", "run2"):
        db = tmp_path / "rebuild/memory/.rebuild_staging" / name / "sqlite/memory_jazn.sqlite3"
        db.parent.mkdir(parents=True)
        sqlite3.connect(db).close()
    report = inspect_memory_layout(project, system_root=root)
    assert report["roles"]["staging"]["status"] == "ambiguous"
    assert report["readiness"]["activation_ready"] is False


def test_host_selected_db_is_not_active_daemon_proof(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, project = fixture(tmp_path, monkeypatch)
    db = tmp_path / "private_memory/sqlite/memory_jazn.sqlite3"
    db.parent.mkdir(parents=True)
    sqlite3.connect(db).close()
    report = inspect_memory_layout(project, system_root=root)
    assert report["roles"]["host_selected_memory"]["status"] == "host_resolved_only"
    assert report["roles"]["host_selected_memory"]["active_daemon_verified"] is False
    assert report["readiness"]["runtime_ready"] is None


def test_symlink_database_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, project = fixture(tmp_path, monkeypatch)
    db = tmp_path / "rebuild/memory/sqlite/memory_jazn.sqlite3"
    db.parent.mkdir(parents=True)
    target = tmp_path / "foreign.sqlite3"
    sqlite3.connect(target).close()
    try:
        db.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("Host cannot create symlinks")
    report = inspect_memory_layout(project, system_root=root)
    assert report["roles"]["target"]["status"] == "unsafe_path"
    assert target.is_file()
