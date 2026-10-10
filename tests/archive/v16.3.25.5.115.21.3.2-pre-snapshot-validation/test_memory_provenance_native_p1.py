from __future__ import annotations

from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3

import pytest

from latka_jazn.tools.memory_rebuild_app.models import RebuildProject, SourceSpec
from latka_jazn.tools.memory_rebuild_app.p1_memory_provenance import (
    _backup, compare_memory_provenance,
)
from latka_jazn.tools.memory_rebuild_app.unified_memory import UnifiedMemoryDatabase


def native_pair(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    system = tmp_path / "system"
    system.mkdir()
    target = tmp_path / "rebuilt" / "memory" / "sqlite" / "memory_jazn.sqlite3"
    host = tmp_path / "private_memory" / "sqlite" / "memory_jazn.sqlite3"
    assert UnifiedMemoryDatabase(target).initialize()["ok"]
    host.parent.mkdir(parents=True)
    with closing(sqlite3.connect(target)) as source:
        source.execute("PRAGMA journal_mode=DELETE")
        with closing(sqlite3.connect(host)) as dest:
            source.backup(dest)
    monkeypatch.setenv("JAZN_MEMORY_ROOT", str(host.parent.parent))
    monkeypatch.setenv("JAZN_RUNTIME_WORKSPACE_DIR", str(tmp_path / "runtime"))
    work = tmp_path / "isolated_temp"
    work.mkdir()
    return system, RebuildProject.create("synthetic", tmp_path / "rebuilt"), target, host, work


def test_real_native_unified_snapshots_match_without_activation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, project, target, host, work = native_pair(tmp_path, monkeypatch)
    source_before = target.read_bytes()
    host_before = host.read_bytes()
    report = compare_memory_provenance(
        project, system_root=root, temp_root=work,
    )
    assert report["roles"]["target"]["state"] == "eligible"
    assert report["roles"]["host_selected_memory"]["state"] == "eligible"
    assert report["comparisons"]["target_vs_host_selected_memory"]["state"] == "equal"
    assert report["temporary_snapshots_cleaned"] is True
    assert report["source_provenance"]["state"] == "unverified"
    assert report["active_runtime_verified"] is False
    assert report["activation_ready"] is False
    assert report["publishing_authorized"] is False
    assert target.read_bytes() == source_before
    assert host.read_bytes() == host_before
    assert list(work.iterdir()) == []


def test_equal_content_with_conflicting_lineage_is_not_false_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, project, target, host, work = native_pair(tmp_path, monkeypatch)
    for path, union in ((target, "first-union"), (host, "second-union")):
        with closing(sqlite3.connect(path)) as con:
            con.execute(
                "INSERT OR REPLACE INTO unified_memory_meta(key,value) VALUES (?,?)",
                ("memory_generation", "same-generation"),
            )
            con.execute(
                "INSERT OR REPLACE INTO unified_memory_meta(key,value) VALUES (?,?)",
                ("source_union_sha256", union),
            )
            con.commit()
    report = compare_memory_provenance(project, system_root=root, temp_root=work)
    result = report["comparisons"]["target_vs_host_selected_memory"]
    assert result["state"] == "equal"
    assert result["lineage"]["state"] == "conflict"


def test_source_sha_attestation_and_source_drift_are_detected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, project, target, _host, work = native_pair(tmp_path, monkeypatch)
    source = tmp_path / "synthetic-export.json"
    source.write_bytes(b"SYNTHETIC_SECRET_BYTES")
    spec = SourceSpec.create(source, pipeline="memory_rebuild")
    project.sources = [spec]
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    with closing(sqlite3.connect(target)) as con:
        con.execute(
            "INSERT OR REPLACE INTO unified_memory_meta(key,value) VALUES (?,?)",
            ("source_restore_status_json", json.dumps([
                {"source_id": spec.source_id, "sha256": digest},
            ])),
        )
        con.commit()
    initial = compare_memory_provenance(project, system_root=root, temp_root=work)
    assert initial["source_provenance"]["state"] == "matching"
    assert "SYNTHETIC_SECRET" not in str(initial)
    source.write_bytes(b"changed-for-drift-test")
    changed = compare_memory_provenance(project, system_root=root, temp_root=work)
    assert changed["source_provenance"]["state"] == "different"
    assert changed["source_provenance"]["changed"] == 1


def test_temporary_snapshots_cannot_be_created_inside_host_memory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, project, _target, host, _work = native_pair(tmp_path, monkeypatch)
    forbidden = host.parent.parent / "scratch"
    forbidden.mkdir()
    outcome = compare_memory_provenance(
        project, system_root=root, temp_root=forbidden,
    )
    assert outcome["issue"] == "unsafe_snapshot_root"
    assert list(forbidden.iterdir()) == []
    assert outcome["publishing_authorized"] is False


def test_online_backup_captures_committed_wal_without_altering_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _root, _project, target, _host, work = native_pair(tmp_path, monkeypatch)
    snap = work / "wal-snapshot.sqlite3"
    with closing(sqlite3.connect(target)) as writer:
        assert writer.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
        writer.execute(
            "INSERT OR REPLACE INTO unified_memory_meta(key,value) VALUES (?,?)",
            ("memory_generation", "wal-committed-generation"),
        )
        writer.commit()
        assert Path(str(target) + "-wal").is_file()
        _backup(target, snap)
        with closing(sqlite3.connect(snap)) as snapshot:
            observed = snapshot.execute(
                "SELECT value FROM unified_memory_meta WHERE key='memory_generation'"
            ).fetchone()
        assert observed == ("wal-committed-generation",)
        assert snap.is_file()
