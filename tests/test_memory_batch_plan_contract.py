from __future__ import annotations

from itertools import permutations
from pathlib import Path
import json

import pytest

from latka_jazn.tools.memory_rebuild_app.adapters.music_analysis import MusicAnalysisAdapter
from latka_jazn.tools.memory_rebuild_app.protocol_engine import _semantic_database_snapshot
from latka_jazn.tools.memory_rebuild_app.unified_memory import UnifiedMemoryDatabase


def _source(path: Path, rows: list[tuple[str, str, str]]) -> Path:
    path.write_text(json.dumps({"analizy": [
        {"id": key, "title": key, "analysis": text, "timestamp": timestamp}
        for key, text, timestamp in rows
    ]}), encoding="utf-8")
    return path


def test_crossed_record_chronology_and_repeated_historical_variant(tmp_path: Path) -> None:
    old, new = "2025-01-01T00:00:00Z", "2025-02-01T00:00:00Z"
    sources = [
        _source(tmp_path / "a.json", [("x", "old x", old), ("y", "new y", new)]),
        _source(tmp_path / "b.json", [("x", "new x", new), ("y", "old y", old)]),
        _source(tmp_path / "c.json", [("x", "old x", old)]),
    ]
    expected = None
    for index, order in enumerate(permutations(sources)):
        store = UnifiedMemoryDatabase(tmp_path / f"result-{index}.sqlite3")
        result = store.import_sources(order, mode="batch")
        assert result["ok"], result
        snapshot = _semantic_database_snapshot(store.path)
        if expected is None:
            expected = snapshot
        assert snapshot == expected
        with store.connect(read_only=True) as con:
            rows = [tuple(row) for row in con.execute(
                "SELECT content,revision FROM memory_l0_records WHERE is_current_revision=1 ORDER BY content"
            )]
            assert rows == [("analysis: new x", 2), ("analysis: new y", 2)]
            assert con.execute("SELECT COUNT(*) FROM memory_l0_records").fetchone()[0] == 4
            assert con.execute("SELECT COUNT(*) FROM memory_l0_occurrences").fetchone()[0] == 5


def test_unresolved_chronology_has_stable_provenance_and_one_adapter_prepare(tmp_path: Path, monkeypatch) -> None:
    sources = [_source(tmp_path / f"{i}.json", [("same", text, "")])
               for i, text in enumerate(("one", "two"))]
    calls: list[Path] = []
    original = MusicAnalysisAdapter.prepare

    def prepare(self, path, probe, settings):
        calls.append(path)
        return original(self, path, probe, settings)

    monkeypatch.setattr(MusicAnalysisAdapter, "prepare", prepare)
    snapshots = []
    for index, order in enumerate((sources, list(reversed(sources)))):
        store = UnifiedMemoryDatabase(tmp_path / f"tie-{index}.sqlite3")
        assert store.import_sources(order, mode="batch")["ok"]
        snapshots.append(_semantic_database_snapshot(store.path))
        with store.connect(read_only=True) as con:
            for row in con.execute("SELECT provenance_json FROM memory_l0_records"):
                decision = json.loads(row[0])["batch_reconstruction"]
                assert decision["unresolved_chronology"] is True
                assert decision["variant_tie_breaker"] == "content_sha256"
    assert snapshots[0] == snapshots[1]
    assert len(calls) == 4


def test_batch_prepare_failure_leaves_destination_absent(tmp_path: Path) -> None:
    source = _source(tmp_path / "valid.json", [("one", "valid", "")])
    store = UnifiedMemoryDatabase(tmp_path / "absent.sqlite3")
    result = store.import_sources([source, tmp_path / "missing.json"], mode="batch")
    assert not result["ok"]
    assert result["errors"][0]["error_type"] == "FileNotFoundError"
    assert not store.path.exists()


def test_explicit_batch_refuses_populated_database_and_incremental_still_updates(tmp_path: Path) -> None:
    source = _source(tmp_path / "old.json", [("same", "old", "")])
    later = _source(tmp_path / "later.json", [("same", "later", "")])
    store = UnifiedMemoryDatabase(tmp_path / "memory.sqlite3")
    assert store.import_sources([source], mode="batch")["ok"]
    before = _semantic_database_snapshot(store.path)
    with pytest.raises(ValueError, match="empty database"):
        store.import_sources([later], mode="batch")
    assert before == _semantic_database_snapshot(store.path)
    assert store.import_sources([later], mode="incremental")["ok"]
    with store.connect(read_only=True) as con:
        current = con.execute("SELECT content,revision FROM memory_l0_records WHERE is_current_revision=1").fetchone()
        assert tuple(current) == ("analysis: later", 2)
