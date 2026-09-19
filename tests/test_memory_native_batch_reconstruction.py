from __future__ import annotations

import json
from pathlib import Path

import pytest

from latka_jazn.tools.memory_rebuild_app.protocol_engine import _semantic_database_snapshot
from latka_jazn.tools.memory_rebuild_app.unified_memory import UnifiedMemoryDatabase


def _sources(root: Path, *, renamed: bool = False) -> list[Path]:
    root.mkdir()
    sources = []
    for index in range(2):
        node = {"id": "message", "parent": None, "children": [], "message": {
            "id": "same-message", "author": {"role": "user"},
            "create_time": 1735689600.0 + index,
            "content": {"content_type": "text", "parts": [f"Synthetic variant {index}"]},
            "metadata": {},
        }}
        graph = {"id": "same-conversation", "title": "Synthetic conversation",
                 "create_time": 1735689600.0, "update_time": 1735689600.0 + index,
                 "current_node": "message", "mapping": {"message": node}}
        suffix = f"moved-{1-index}" if renamed else str(index)
        chat = root / f"chat-{suffix}.json"
        chat.write_text(json.dumps([graph]), encoding="utf-8")
        journal = root / f"dziennik-{suffix}.jsonl"
        journal.write_text(json.dumps({"id": "same-entry", "title": "Synthetic journal",
            "content": f"Journal variant {index}", "data": f"2025-0{index+1}-01T00:00:00Z"}) + "\n", encoding="utf-8")
        sources.extend((chat, journal))
    return sources


@pytest.mark.parametrize("relocated", [False, True])
def test_native_conflicts_preserve_full_batch_snapshot(tmp_path: Path, relocated: bool) -> None:
    sources = _sources(tmp_path / "original")
    reverse_sources = _sources(tmp_path / "relocated", renamed=True) if relocated else sources
    snapshots = []
    conflicts = []
    for name, order in (("normal", sources), ("reverse", list(reversed(reverse_sources)))):
        store = UnifiedMemoryDatabase(tmp_path / f"{name}.sqlite3")
        result = store.import_sources(order, mode="batch")
        assert result["ok"], result
        with store.connect(read_only=True) as con:
            rows = [tuple(row) for row in con.execute(
                "SELECT conflict_id,conversation_id,changed_node_ids_json,resolution_status,resolution_reason "
                "FROM import_conflicts ORDER BY conflict_id"
            )]
            assert len(rows) == 1
            assert rows[0][3] == "unresolved"
            assert con.execute("PRAGMA foreign_key_check").fetchall() == []
        conflicts.append(rows)
        snapshots.append(_semantic_database_snapshot(store.path))
    assert conflicts[0] == conflicts[1]
    assert snapshots[0] == snapshots[1]
