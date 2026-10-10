from __future__ import annotations

from pathlib import Path
import sqlite3

import pytest

from latka_jazn.memory.availability import runtime_memory_storage_path
from latka_jazn.memory.database_paths import resolve_sqlite_directory
from latka_jazn.memory.memory_root import memory_path, normalize_memory_relative_path
from latka_jazn.memory.runtime_memory_install import resolve_memory_tier_database_path
from latka_jazn.memory.unified_memory_runtime import probe_unified_memory_database
from latka_jazn.tools.memory_rebuild_app.sqlite_inspector import resolve_database_root
from latka_jazn.tools.memory_restore_storage import resolve_database_paths


@pytest.fixture
def isolated_memory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    runtime = tmp_path / "system"
    memory = tmp_path / "memory"
    runtime.mkdir()
    memory.mkdir()
    monkeypatch.setenv("JAZN_MEMORY_ROOT", str(memory))
    monkeypatch.setenv("JAZN_RUNTIME_WORKSPACE_DIR", str(tmp_path / "workspace"))
    monkeypatch.setenv("JAZN_MEMORY_MODE", "optional")
    monkeypatch.delenv("JAZN_MEMORY_TIER_DB", raising=False)
    return runtime, memory


@pytest.mark.parametrize("relative", [
    "sqlite/example.sqlite3", "memory/sqlite/example.sqlite3",
    "memory\\sqlite\\example.sqlite3", "MeMoRy/sqlite/example.sqlite3",
])
def test_memory_and_tier_paths_share_one_normalization(
    isolated_memory: tuple[Path, Path], relative: str,
) -> None:
    runtime, memory = isolated_memory
    expected = memory / "sqlite" / "example.sqlite3"
    assert memory_path(runtime, relative) == expected
    assert resolve_memory_tier_database_path(runtime, configured=relative) == expected
    assert not expected.exists()
    assert not (memory / "sqlite").exists()


@pytest.mark.parametrize("relative", [
    "memory/memory/sqlite/example.sqlite3", "MEMORY\\memory\\sqlite\\example.sqlite3",
    "../example.sqlite3", "sqlite/../example.sqlite3", "sqlite\\..\\example.sqlite3",
    "C:example.sqlite3", "C:\\example.sqlite3", "/example.sqlite3",
    "\\\\server\\share\\example.sqlite3", "", ".", "memory",
])
def test_memory_paths_reject_unsafe_aliases_consistently(
    isolated_memory: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch, relative: str,
) -> None:
    runtime, memory = isolated_memory
    with pytest.raises(ValueError):
        normalize_memory_relative_path(relative)
    with pytest.raises(ValueError):
        memory_path(runtime, relative)
    with pytest.raises(ValueError):
        runtime_memory_storage_path(runtime, relative, mode="off")
    with pytest.raises(ValueError):
        resolve_memory_tier_database_path(runtime, configured=relative)
    if relative:
        monkeypatch.setenv("JAZN_MEMORY_TIER_DB", relative)
        with pytest.raises(ValueError):
            resolve_memory_tier_database_path(runtime)
    assert list(memory.iterdir()) == []


def test_absolute_configured_tier_keeps_selected_memory_path(
    isolated_memory: tuple[Path, Path],
) -> None:
    runtime, memory = isolated_memory
    configured = memory / "sqlite" / "example.sqlite3"
    assert resolve_memory_tier_database_path(runtime, configured=configured) == configured


def test_absolute_configured_tier_rejects_memory_nested_in_memory(
    isolated_memory: tuple[Path, Path],
) -> None:
    runtime, memory = isolated_memory
    with pytest.raises(ValueError, match="duplicated"):
        resolve_memory_tier_database_path(
            runtime, configured=memory / "memory" / "sqlite" / "example.sqlite3",
        )


def test_memory_path_rejects_symlink_escape(
    isolated_memory: tuple[Path, Path], tmp_path: Path,
) -> None:
    runtime, memory = isolated_memory
    outside = tmp_path / "outside"
    outside.mkdir()
    link = memory / "sqlite"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"host cannot create a directory symlink: {exc}")
    with pytest.raises(ValueError, match="escapes"):
        memory_path(runtime, "sqlite/example.sqlite3")
    assert list(outside.iterdir()) == []


@pytest.mark.parametrize("layout", ["system", "memory", "sqlite", "custom", "file"])
def test_restore_and_inspector_resolve_existing_memory_layouts(tmp_path: Path, layout: str) -> None:
    if layout == "system":
        selected = tmp_path / "system"
        database_dir = selected / "memory" / "sqlite"
    elif layout == "memory":
        selected = tmp_path / "memory"
        database_dir = selected / "sqlite"
    elif layout == "custom":
        selected = tmp_path / "private-store"
        database_dir = selected / "sqlite"
    else:
        database_dir = tmp_path / "sqlite"
        selected = database_dir if layout == "sqlite" else database_dir / "memory_jazn.sqlite3"
    database_dir.mkdir(parents=True)
    database = database_dir / "memory_jazn.sqlite3"
    with sqlite3.connect(database) as con:
        con.execute("CREATE TABLE foreign_data(id INTEGER PRIMARY KEY)")
    before = database.read_bytes()
    assert resolve_database_root(selected) == database_dir
    assert resolve_database_paths(selected)["memory_jazn"] == database
    assert database.read_bytes() == before
    assert "memory/memory" not in database.as_posix()
    probe = probe_unified_memory_database(database)
    assert probe["native_unified"] is False
    assert probe["memory_search_ready"] is False
    assert database.read_bytes() == before


def test_missing_path_fallback_preserves_explicit_roles_and_caller_contract(tmp_path: Path) -> None:
    memory = tmp_path / "memory"
    sqlite = tmp_path / "sqlite"
    ambiguous = tmp_path / "target"
    assert resolve_database_root(memory) == memory / "sqlite"
    assert resolve_database_paths(memory)["memory_jazn"] == memory / "sqlite" / "memory_jazn.sqlite3"
    assert resolve_database_root(sqlite) == sqlite
    assert resolve_database_paths(sqlite)["memory_jazn"] == sqlite / "memory_jazn.sqlite3"
    assert resolve_database_root(ambiguous) == ambiguous
    assert resolve_database_paths(ambiguous)["memory_jazn"] == ambiguous / "memory" / "sqlite" / "memory_jazn.sqlite3"
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("relative", ["memory/memory/sqlite", "target/../sqlite", "C:sqlite"])
def test_database_directory_rejects_ambiguous_or_unsafe_input(relative: str) -> None:
    with pytest.raises(ValueError):
        resolve_sqlite_directory(relative, database_filenames=("memory_jazn.sqlite3",))


def test_database_discovery_rejects_nested_symlink_escape(tmp_path: Path) -> None:
    root = tmp_path / "memory"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    try:
        (root / "sqlite").symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"host cannot create a directory symlink: {exc}")
    with pytest.raises(ValueError, match="escapes"):
        resolve_database_root(root)
