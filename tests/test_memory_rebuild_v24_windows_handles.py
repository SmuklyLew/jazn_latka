from __future__ import annotations

from pathlib import Path
import os

from latka_jazn.tools.memory_rebuild_app.unified_memory import (
    CANONICAL_DATABASE_NAME,
    UnifiedMemoryDatabase,
)


def test_backup_releases_source_and_destination_handles_before_return(tmp_path: Path) -> None:
    database = tmp_path / CANONICAL_DATABASE_NAME
    store = UnifiedMemoryDatabase(database)
    assert store.initialize()["ok"]

    backup = store.backup(tmp_path / "memory-backup.sqlite3")
    assert backup.is_file()

    moved = tmp_path / "memory-backup-moved.sqlite3"
    os.replace(backup, moved)
    moved.unlink()

    assert not backup.exists()
    assert not moved.exists()
