from __future__ import annotations

from pathlib import Path

from latka_jazn.core import host_spawn_diagnostics
from latka_jazn.memory.memory_root import (
    default_memory_root,
    legacy_memory_root,
    resolve_memory_root_diagnostic,
)


def test_empty_canonical_placeholder_is_reported_but_legacy_stays_selected(
    tmp_path: Path,
    monkeypatch,
) -> None:
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir()
    canonical = default_memory_root(runtime_root)
    canonical.mkdir(parents=True)
    legacy = legacy_memory_root(runtime_root)
    db = legacy / "sqlite" / "memory_jazn.sqlite3"
    db.parent.mkdir(parents=True)
    db.write_bytes(b"synthetic")

    monkeypatch.delenv("JAZN_MEMORY_ROOT", raising=False)
    report = resolve_memory_root_diagnostic(runtime_root)

    assert report["selected"] == str(legacy.resolve())
    assert report["selection_source"] == "legacy_compatibility"
    assert report["empty_canonical_placeholder_detected"] is True
    assert report["canonical_has_payload"] is False
    assert report["legacy_has_payload"] is True
    assert report["private_content_read"] is False


def test_explicit_root_diagnostic_remains_authoritative(
    tmp_path: Path,
    monkeypatch,
) -> None:
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir()
    monkeypatch.setenv("JAZN_MEMORY_ROOT", "explicit-memory")

    report = resolve_memory_root_diagnostic(runtime_root)

    assert report["selection_source"] == "environment"
    assert report["explicit_configured"] is True
    assert Path(report["selected"]).name == "explicit-memory"


def test_post_spawn_diagnostics_reports_process_and_memory_metadata(
    tmp_path: Path,
    monkeypatch,
) -> None:
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir()
    memory_root = default_memory_root(runtime_root)
    database = memory_root / "sqlite" / "memory_jazn.sqlite3"
    database.parent.mkdir(parents=True)
    database.write_bytes(b"placeholder")

    monkeypatch.delenv("JAZN_MEMORY_ROOT", raising=False)
    monkeypatch.setattr(
        host_spawn_diagnostics,
        "probe_unified_memory_database",
        lambda path: {
            "database": str(path),
            "memory_search_ready": True,
            "full_autobiographical_recall_ready": True,
        },
    )

    report = host_spawn_diagnostics.build_host_spawn_diagnostics(runtime_root)

    assert report["ok"] is True
    assert report["process_created"] is True
    assert isinstance(report["pid"], int)
    assert report["pid"] > 0
    assert report["memory"]["resolved_root"] == str(memory_root.resolve())
    assert report["memory"]["canonical_database"] == str(database.resolve())
    assert report["memory"]["canonical_database_exists"] is True
    assert report["memory"]["private_content_read"] is False
    assert report["native_memory_probe"]["memory_search_ready"] is True
