from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from latka_jazn.config import JaznConfig
from latka_jazn.tools.memory_validation import (
    _manifest_targets,
    discover_memory_validation_targets,
)


def _manifest(root: Path, *, shard_path: str, active: str = "0001") -> Path:
    path = root / "sqlite/runtime_write_v1/runtime_memory_shards.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({
            "schema_version": "jazn_sqlite_shards/v1",
            "logical_database": "chat_context",
            "role": "canonical_runtime_conversation_memory",
            "active_write_shard": active,
            "max_file_bytes": 1024 * 1024 * 1024,
            "shards": [
                {
                    "shard_id": "0001",
                    "path": shard_path,
                    "role": "active_write",
                    "created_at_utc": "2026-10-12T00:00:00+00:00",
                    "sealed_at_utc": None,
                    "size_bytes": 0,
                    "sha256": None,
                    "note": "synthetic legacy path",
                }
            ],
        }),
        encoding="utf-8",
    )
    return path


@pytest.mark.parametrize("shard_path", [
    "sqlite/runtime_write_v1/runtime_memory.sqlite3",
    "memory/sqlite/runtime_write_v1/runtime_memory.sqlite3",
    r"memory\sqlite\runtime_write_v1\runtime_memory.sqlite3",
])
def test_memory_manifest_path_is_bound_once_to_memory_root(
    tmp_path: Path, shard_path: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    memory_root = tmp_path / "workspace_runtime/memory"
    manifest = _manifest(memory_root, shard_path=shard_path)
    # This fixture tests an explicitly attached legacy MEMORY source. Runtime
    # writers must not switch from core_state merely because SQLite exists.
    legacy_source = memory_root / "raw" / "dziennik.json"
    legacy_source.parent.mkdir(parents=True, exist_ok=True)
    legacy_source.write_text("[]", encoding="utf-8")
    monkeypatch.setenv("JAZN_MEMORY_ROOT", str(memory_root))
    monkeypatch.setenv("JAZN_MEMORY_MODE", "optional")
    expected = memory_root / "sqlite/runtime_write_v1/runtime_memory.sqlite3"
    expected.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(expected) as con:
        con.execute("CREATE TABLE item(id INTEGER PRIMARY KEY)")

    issues: list[dict[str, str]] = []
    targets = _manifest_targets(memory_root, manifest, "conversation", issues=issues)
    assert issues == []
    assert len(targets) == 1
    assert Path(targets[0].path) == expected.resolve()
    assert targets[0].required is True
    assert Path(targets[0].path).is_file()
    assert "memory/memory/" not in targets[0].path.replace("\\", "/")

    # The read-only operational shard resolver must agree with the validator.
    config = JaznConfig(root=tmp_path / "runtime")
    assert config.memory_availability.persistent_memory_enabled is True
    assert config.memory_root == memory_root.resolve()
    assert config.memory_db_path_readonly == expected.resolve()
    discovered = discover_memory_validation_targets(config.root)
    assert sum(target.path == str(expected.resolve()) for target in discovered) == 1


@pytest.mark.parametrize("shard_path", [
    "memory/memory/sqlite/runtime_write_v1/runtime_memory.sqlite3",
    "../outside.sqlite3",
    r"C:\private\outside.sqlite3",
    r"memory\..\private.sqlite3",
])
def test_unsafe_manifest_path_is_rejected_and_reported(tmp_path: Path, shard_path: str) -> None:
    memory_root = tmp_path / "workspace_runtime/memory"
    manifest = _manifest(memory_root, shard_path=shard_path)
    issues: list[dict[str, str]] = []
    targets = _manifest_targets(memory_root, manifest, "conversation", issues=issues)
    assert targets == []
    assert [item["reason"] for item in issues] == ["shard_path_unsafe"]
    assert all(item["role"] == "conversation" for item in issues)


def test_broken_manifest_cannot_silently_look_healthy(tmp_path: Path) -> None:
    memory_root = tmp_path / "workspace_runtime/memory"
    manifest = _manifest(memory_root, shard_path="sqlite/runtime_write_v1/runtime_memory.sqlite3")
    manifest.write_text("{malformed", encoding="utf-8")
    issues: list[dict[str, str]] = []
    assert _manifest_targets(memory_root, manifest, "conversation", issues=issues) == []
    assert issues[0]["reason"] == "manifest_unreadable"
