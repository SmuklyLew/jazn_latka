import json
from pathlib import Path

from latka_jazn.tools._active_extraction_cache_impl import _active_storage_from_bootstrap


def test_bootstrap_storage_stays_within_selected_system(tmp_path: Path) -> None:
    root = tmp_path / "SYSTEM"
    root.mkdir()
    data = root / "memory/sqlite/conversation_archive_v1/conversation_archive_0001.sqlite3"
    data.parent.mkdir(parents=True)
    data.touch()
    foreign = tmp_path / "another.sqlite3"
    foreign.touch()
    (root / "BOOTSTRAP_JAZN_CURRENT.json").write_text(json.dumps({
        "active_database": data.relative_to(root).as_posix(),
        "active_audit_database": "../another.sqlite3",
    }))
    assert _active_storage_from_bootstrap(root, None)["active_audit_database"] is None
