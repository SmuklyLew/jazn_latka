from __future__ import annotations

from pathlib import Path
import sqlite3

from latka_jazn.config import JaznConfig
from latka_jazn.memory.memory_cloud_snapshot_runtime import MemoryCloudSnapshotRuntime


def _db(path: Path, marker: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as con:
        con.execute("CREATE TABLE IF NOT EXISTS t(value TEXT NOT NULL)")
        con.execute("INSERT INTO t(value) VALUES(?)", (marker,))
        con.commit()


def test_snapshot_plan_discovers_core_databases_without_network_or_mutation(tmp_path, monkeypatch) -> None:
    tier = tmp_path / "memory/sqlite/runtime_write_v2/runtime_memory.sqlite3"
    runtime = tmp_path / "memory/sqlite/runtime_write_v1/runtime_memory.sqlite3"
    sidecar = tmp_path / "memory/sqlite/runtime_write_v1/normalization_sidecar.sqlite3"
    recovered = tmp_path / "memory/sqlite/recovery_current/runtime_memory_recovered.sqlite3"
    for idx, path in enumerate((tier, runtime, sidecar, recovered)):
        _db(path, str(idx))
    cfg = JaznConfig(root=tmp_path)
    monkeypatch.setattr(
        "latka_jazn.memory.memory_cloud_snapshot_runtime.status_daemon",
        lambda _cfg: {"active_state": "inactive", "pid_alive": False},
    )
    plan = MemoryCloudSnapshotRuntime(cfg).plan(profile="core")
    logical = {source.logical_path for source in plan.sources}
    assert "memory/sqlite/runtime_write_v2/runtime_memory.sqlite3" in logical
    assert "memory/sqlite/runtime_write_v1/runtime_memory.sqlite3" in logical
    assert "memory/sqlite/runtime_write_v1/normalization_sidecar.sqlite3" in logical
    assert "memory/sqlite/recovery_current/runtime_memory_recovered.sqlite3" in logical
    assert plan.runtime_stopped is True
    assert plan.source_memory_generation.startswith("local-sqlite-generation:")
    assert plan.base_remote_seq == 0
    assert plan.event_chain_head_sha256 is None


def test_all_sqlite_profile_excludes_restore_and_staging_roots(tmp_path, monkeypatch) -> None:
    _db(tmp_path / "memory/sqlite/runtime_write_v2/runtime_memory.sqlite3", "canonical")
    _db(tmp_path / "memory/sqlite/conversation_archive_v1/archive.sqlite3", "archive")
    _db(tmp_path / "memory/sqlite/staging_v1/temp.sqlite3", "staging")
    _db(tmp_path / "memory/sqlite/restore-old/temp.sqlite3", "restore")
    monkeypatch.setattr(
        "latka_jazn.memory.memory_cloud_snapshot_runtime.status_daemon",
        lambda _cfg: {"active_state": "inactive", "pid_alive": False},
    )
    plan = MemoryCloudSnapshotRuntime(JaznConfig(root=tmp_path)).plan(profile="all-sqlite")
    logical = {source.logical_path for source in plan.sources}
    assert "memory/sqlite/runtime_write_v2/runtime_memory.sqlite3" in logical
    assert "memory/sqlite/conversation_archive_v1/archive.sqlite3" in logical
    assert all("staging_v1" not in path and "restore-old" not in path for path in logical)


def test_snapshot_plan_reports_running_daemon_as_not_snapshot_safe(tmp_path, monkeypatch) -> None:
    _db(tmp_path / "memory/sqlite/runtime_write_v2/runtime_memory.sqlite3", "canonical")
    monkeypatch.setattr(
        "latka_jazn.memory.memory_cloud_snapshot_runtime.status_daemon",
        lambda _cfg: {"active_state": "active_trusted", "pid_alive": True},
    )
    plan = MemoryCloudSnapshotRuntime(JaznConfig(root=tmp_path)).plan(profile="core")
    assert plan.runtime_stopped is False
