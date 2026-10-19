from __future__ import annotations

from pathlib import Path
import sqlite3

import pytest

from latka_jazn.memory.database_identity import inspect_memory_database
from latka_jazn.memory.memory_tier_store import MemoryTierStore
from latka_jazn.memory.runtime_memory_install import initialize_transactional_memory_store
from latka_jazn.tools.configuration_studio import (
    ConfigValidationError, profile_digest, read_profile, restore_previous_profile,
    save_profile, validate_values,
)


@pytest.fixture
def system(tmp_path: Path) -> Path:
    root = tmp_path / "system"
    (root / "latka_jazn").mkdir(parents=True)
    (root / "main.py").write_text("# synthetic", encoding="utf-8")
    (root / "latka_jazn" / "version.py").write_text("# synthetic", encoding="utf-8")
    return root


@pytest.mark.parametrize("value", [
    "../foreign.db", "sqlite/../foreign.db", "C:foreign.db", "C:/foreign.db",
    "/foreign.db", "memory/sqlite/foreign.db", "memory/memory/sqlite/foreign.db",
    "sqlite/file.json", "sqlite/file.db:stream",
])
def test_database_profile_rejects_unsafe_paths(system: Path, value: str) -> None:
    with pytest.raises(ConfigValidationError):
        validate_values(system, {"JAZN_MEMORY_TIER_DB": value})


def test_database_profile_roundtrip_backup_without_creating_database(system: Path, tmp_path: Path) -> None:
    memory = tmp_path / "private"
    workspace = tmp_path / "workspace"
    values = {"JAZN_MEMORY_ROOT": str(memory), "JAZN_MEMORY_TIER_DB": "sqlite/first.sqlite3"}
    save_profile(system, values, workspace=workspace)
    save_profile(system, {**values, "JAZN_MEMORY_TIER_DB": "sqlite/second.sqlite3"},
                 workspace=workspace, expected_sha256=profile_digest(system, workspace=workspace))
    restore_previous_profile(system, workspace=workspace,
                             expected_sha256=profile_digest(system, workspace=workspace))
    assert read_profile(system, workspace=workspace) == values
    assert not memory.exists()


def test_legacy_database_name_does_not_authorize_schema_mutation(system: Path, tmp_path: Path) -> None:
    memory = tmp_path / "private"
    memory.mkdir()
    database = memory / "memory_jazn.sqlite3"
    with sqlite3.connect(database) as con:
        con.execute("CREATE TABLE private_legacy(id INTEGER PRIMARY KEY, text TEXT)")
        con.execute("INSERT INTO private_legacy VALUES(1, 'synthetic fixture')")
    before = database.read_bytes()
    report = inspect_memory_database(database)
    assert report["kind"] == "legacy_or_foreign"
    assert report["compatible"] is False
    with pytest.raises(ConfigValidationError, match="schemat"):
        validate_values(system, {"JAZN_MEMORY_ROOT": str(memory), "JAZN_MEMORY_TIER_DB": database.name})
    assert database.read_bytes() == before


def test_transactional_schema_is_verified_without_writes(system: Path, tmp_path: Path) -> None:
    memory = tmp_path / "private"
    database = memory / "tier.sqlite3"
    with MemoryTierStore(database):
        pass
    before = database.read_bytes()
    report = inspect_memory_database(database)
    assert report["kind"] == "transactional"
    assert report["compatible"] is True
    assert validate_values(system, {"JAZN_MEMORY_ROOT": str(memory), "JAZN_MEMORY_TIER_DB": database.name})
    assert database.read_bytes() == before


def test_corrupt_database_is_reported_without_mutation(tmp_path: Path) -> None:
    database = tmp_path / "corrupt.sqlite3"
    database.write_bytes(b"not a sqlite database")
    assert inspect_memory_database(database)["kind"] == "invalid"
    assert database.read_bytes() == b"not a sqlite database"


def test_runtime_preflight_does_not_initialize_foreign_database(
    system: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    memory = tmp_path / "memory"
    (memory / "raw").mkdir(parents=True)
    (memory / "raw" / "chat.html").write_text("synthetic", encoding="utf-8")
    database = memory / "foreign.sqlite3"
    with sqlite3.connect(database) as con:
        con.execute("CREATE TABLE legacy_data(id INTEGER)")
    before = database.read_bytes()
    monkeypatch.setenv("JAZN_MEMORY_ROOT", str(memory))
    monkeypatch.setenv("JAZN_MEMORY_MODE", "optional")
    report = initialize_transactional_memory_store(system, configured="foreign.sqlite3")
    assert report["ok"] is False
    assert "memory_database_schema_rejected" in report["error"]
    assert database.read_bytes() == before
