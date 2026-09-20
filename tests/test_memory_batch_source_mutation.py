from __future__ import annotations

import json
from pathlib import Path
import zipfile

import pytest

from latka_jazn.tools.memory_rebuild_app.batch_plan import BatchPlan
from latka_jazn.tools.memory_rebuild_app.unified_memory import UnifiedMemoryDatabase


def _write_source(path: Path, kind: str, text: str) -> None:
    if kind == "journal":
        path.write_text(json.dumps({"id": "entry", "content": text,
            "data": "2025-01-01T00:00:00Z"}) + "\n", encoding="utf-8")
        return
    payload = json.dumps([{"id": "conversation", "title": "Synthetic source",
        "current_node": "node", "mapping": {"node": {"id": "node", "parent": None,
        "children": [], "message": {"id": "message", "author": {"role": "user"},
        "create_time": 1735689600.0,
        "content": {"content_type": "text", "parts": [text]}}}}}])
    if kind == "directory":
        path.mkdir(exist_ok=True)
        (path / "conversations.json").write_text(payload, encoding="utf-8")
    elif kind == "zip":
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("conversations.json", payload)
    else:
        path.write_text(payload, encoding="utf-8")


@pytest.mark.parametrize("kind", ["json", "zip", "directory", "journal"])
@pytest.mark.parametrize("phase", ["after_prepare", "before_native"])
def test_batch_refuses_source_changed_after_preparation(tmp_path: Path, monkeypatch, kind: str, phase: str) -> None:
    suffix = {"json": ".json", "zip": ".zip", "directory": "", "journal": ".jsonl"}[kind]
    source = tmp_path / ("dziennik" + suffix if kind == "journal" else "export" + suffix)
    _write_source(source, kind, "Original source text")
    store = UnifiedMemoryDatabase(tmp_path / "destination.sqlite3")
    if phase == "after_prepare":
        original_add = BatchPlan.add

        def add(plan, prepared):
            original_add(plan, prepared)
            _write_source(source, kind, "Changed source text")

        monkeypatch.setattr(BatchPlan, "add", add)
    else:
        original_initialize = store.ensure_initialized

        def initialize():
            result = original_initialize()
            _write_source(source, kind, "Changed source text")
            return result

        monkeypatch.setattr(store, "ensure_initialized", initialize)

    result = store.import_sources([source], mode="batch")
    assert result["ok"] is False, "Changed native input must never certify the prepared L0 plan"
    assert result["errors"]
    assert "source changed" in result["errors"][0]["error"].lower()
    assert result["automatic_l2"] is False
    assert result["automatic_l3"] is False
    assert result["automatic_activation"] is False
    if phase == "after_prepare":
        assert not store.path.exists()
    else:
        with store.connect(read_only=True) as connection:
            for table in ("memory_l0_records", "memory_l0_sources", "conversations", "journal_entries"):
                assert connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
            assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
