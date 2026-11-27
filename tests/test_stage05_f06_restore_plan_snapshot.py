"""F06: legacy restore planning reads the exact source into a private staging DB."""
from __future__ import annotations

from contextlib import closing
from pathlib import Path
import sqlite3
from types import SimpleNamespace
from typing import Any

import pytest

from latka_jazn.db import runtime_sqlite as policy
from latka_jazn.tools import memory_restore_runner as runner
from latka_jazn.tools.memory_restore import (
    MemoryRestoreOrchestrator, MemoryRestoreSettings, resolve_database_paths,
)


def _fixture(tmp_path: Path) -> tuple[MemoryRestoreOrchestrator, Path, Path]:
    target = tmp_path / "synthetic # 50% root"
    source = tmp_path / "input.json"
    source.write_text("[]", encoding="utf-8")
    settings = MemoryRestoreSettings(
        source_directory=str(tmp_path), target_root=str(target), mode="developer",
    )
    archive = resolve_database_paths(target)["archive_chats"]
    archive.parent.mkdir(parents=True)
    with closing(sqlite3.connect(archive)) as connection:
        connection.execute("CREATE TABLE sample(value TEXT)")
        connection.execute("INSERT INTO sample VALUES('synthetic')")
        connection.commit()
    return MemoryRestoreOrchestrator(settings, tool_root=tmp_path / "repo"), archive, source


@pytest.mark.parametrize("fixed", [False, True])
def test_planning_snapshot_reads_exact_encoded_source_into_fresh_delete_db(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fixed: bool,
) -> None:
    restore, archive, source = _fixture(tmp_path)
    before = archive.read_bytes()
    entries_before = {path.name for path in tmp_path.iterdir()}
    inspected: list[Path] = []
    monkeypatch.setattr(policy, "sqlite_wal_reset_fix_available", lambda *_a: fixed)
    monkeypatch.setattr(runner, "detect_source", lambda path: {
        "kind": "chat_export", "canonical_conversations_available": True, "path": str(path),
    })

    def inspect(_source: Path, staging: Path) -> Any:
        assert not staging.is_relative_to(tmp_path / "synthetic # 50% root")
        with closing(sqlite3.connect(staging)) as connection:
            assert connection.execute("SELECT value FROM sample").fetchone()[0] == "synthetic"
            assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
        inspected.append(staging)
        return SimpleNamespace(to_dict=lambda: {})

    def simulate(*_args: Any, **_kwargs: Any) -> Any:
        return SimpleNamespace(to_dict=lambda: {"validation": {"ok": True}})

    monkeypatch.setattr(restore.importer, "plan", inspect)
    monkeypatch.setattr(restore.importer, "import_one", simulate)
    result = restore.plan([source])
    assert result.ok and len(result.chats) == 1
    assert len(inspected) == 1 and not inspected[0].exists()
    assert archive.read_bytes() == before
    assert {path.name for path in tmp_path.iterdir()} == entries_before


def test_planning_closes_source_when_staging_open_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    restore, archive, source = _fixture(tmp_path)
    before = archive.read_bytes()
    opened: list[sqlite3.Connection] = []

    def observe(path: Path) -> sqlite3.Connection:
        connection = policy.connect_runtime_readonly(path)
        opened.append(connection)
        assert connection.execute("PRAGMA query_only").fetchone()[0] == 1
        return connection

    def refuse(_path: Path) -> sqlite3.Connection:
        raise OSError("synthetic staging failure")

    monkeypatch.setattr(runner, "connect_runtime_readonly", observe)
    monkeypatch.setattr(runner, "connect_new_portable_sqlite", refuse)
    with pytest.raises(OSError, match="synthetic staging failure"):
        restore.plan([source])
    assert len(opened) == 1
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        opened[0].execute("SELECT 1")
    assert archive.read_bytes() == before
