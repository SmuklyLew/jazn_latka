from contextlib import closing
from pathlib import Path
import sqlite3

import pytest

from latka_jazn.memory.database_identity import initialize_database_identity, read_database_identity
from latka_jazn.memory.living_memory_gateway import LivingMemoryGateway
from latka_jazn.tools.memory_rebuild_app.settings import (
    MemoryRebuildToolSettings, load_tool_settings, resolve_settings_path, save_tool_settings,
)


def test_gateway_finds_real_database_when_given_memory_root(tmp_path: Path) -> None:
    memory = tmp_path / "memory"
    database = memory / "sqlite" / "memory_jazn.sqlite3"
    database.parent.mkdir(parents=True)
    with closing(sqlite3.connect(database)) as con:
        con.execute("CREATE TABLE synthetic(value TEXT)")
        con.execute("INSERT INTO synthetic VALUES('located')")
        con.commit()
    directory = LivingMemoryGateway._as_sqlite_dir(memory)
    assert directory == memory / "sqlite"
    with closing(sqlite3.connect((directory / database.name).as_uri() + "?mode=ro", uri=True)) as con:
        assert con.execute("SELECT value FROM synthetic").fetchone() == ("located",)
    assert not (memory / "memory").exists()


def test_identity_api_remains_compatible_with_existing_clients() -> None:
    with closing(sqlite3.connect(":memory:")) as con:
        created = initialize_database_identity(con, schema_identity="synthetic", schema_version_number=1)
        observed = read_database_identity(con)
        assert observed is not None
        assert observed.database_uuid == created.database_uuid
        assert observed.schema_identity == "synthetic"


def test_memory_settings_workspace_roundtrip_and_system_rejection(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    system = tmp_path / "system"
    (system / "latka_jazn").mkdir(parents=True)
    (system / "latka_jazn" / "version.py").write_text("", encoding="utf-8")
    (system / "main.py").write_text("", encoding="utf-8")
    workspace = tmp_path / "workspace_runtime"
    monkeypatch.setenv("JAZN_RUNTIME_WORKSPACE_DIR", str(workspace))
    monkeypatch.delenv("JAZN_MEMORY_REBUILD_SETTINGS", raising=False)
    expected = workspace / "memory_rebuild_settings.json"
    assert resolve_settings_path(tool_root=system) == expected
    settings = MemoryRebuildToolSettings()
    assert save_tool_settings(settings, tool_root=system) == expected
    assert load_tool_settings(tool_root=system) == settings
    with pytest.raises(ValueError):
        save_tool_settings(settings, system / "memory_rebuild_settings.json", tool_root=system)
