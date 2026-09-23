from __future__ import annotations

from pathlib import Path
import json

import pytest

from latka_jazn.tools.memory_rebuild_app.protocol_engine import _semantic_database_snapshot
from latka_jazn.tools.memory_rebuild_app.unified_memory import UnifiedMemoryDatabase


def _sources(root: Path, *, relocated: bool = False) -> tuple[Path, Path]:
    root.mkdir(parents=True)
    paths = []
    for index, (content, date) in enumerate((
        ("Earlier interpretation", "2025-01-01T00:00:00Z"),
        ("Later interpretation", "2025-02-01T00:00:00Z"),
    )):
        name = f"renamed-{1-index}.json" if relocated else f"source-{index}.json"
        path = root / name
        path.write_text(json.dumps({"analizy": [{
            "id": "same-logical-analysis", "title": "Synthetic song",
            "analysis": content, "timestamp": date,
        }]}), encoding="utf8")
        paths.append(path)
    return paths[0], paths[1]


def _state(store: UnifiedMemoryDatabase) -> dict[str, object]:
    with store.connect(read_only=True) as con:
        records = [tuple(row) for row in con.execute(
            "SELECT logical_key,content,revision,is_current_revision,record_id "
            "FROM memory_l0_records ORDER BY logical_key,revision,record_id"
        )]
        occurrences = [tuple(row) for row in con.execute(
            "SELECT logical_key,revision,source_id,source_record_id "
            "FROM memory_l0_occurrences ORDER BY logical_key,revision,source_id,source_record_id"
        )]
    return {"records": records, "occurrences": occurrences,
            "semantic_snapshot": _semantic_database_snapshot(store.path)}


@pytest.mark.parametrize("relocated", [False, True])
def test_batch_reconstruction_is_order_and_location_independent(tmp_path: Path, relocated: bool) -> None:
    """A closed source union yields identical revision identities, links and semantic state."""
    normal_sources = _sources(tmp_path / "inputs")
    reverse_sources = _sources(tmp_path / "other-inputs", relocated=True) if relocated else normal_sources
    normal = UnifiedMemoryDatabase(tmp_path / "normal.sqlite3")
    reverse = UnifiedMemoryDatabase(tmp_path / "reverse.sqlite3")
    assert normal.import_sources(normal_sources)["ok"]
    assert reverse.import_sources(reversed(reverse_sources))["ok"]
    normal_state, reverse_state = _state(normal), _state(reverse)
    assert normal_state == reverse_state
    for store in (normal, reverse):
        with store.connect(read_only=True) as con:
            current = con.execute(
                "SELECT content,revision FROM memory_l0_records WHERE is_current_revision=1"
            ).fetchall()
            assert [tuple(row) for row in current] == [("analysis: Later interpretation", 2)]


def test_explicit_incremental_import_keeps_revision_sequence(tmp_path: Path) -> None:
    """Explicit later imports still create revisions, while an identical repeat links evidence."""
    earlier, later = _sources(tmp_path / "inputs")
    store = UnifiedMemoryDatabase(tmp_path / "incremental.sqlite3")
    assert store.import_source(earlier).report["ok"]
    assert store.import_source(later).report["ok"]
    before = _state(store)
    assert store.import_source(later).report["ok"]
    assert _state(store) == before
    with store.connect(read_only=True) as con:
        revisions = [tuple(row) for row in con.execute(
            "SELECT revision,is_current_revision FROM memory_l0_records ORDER BY revision"
        )]
    assert revisions == [(1, 0), (2, 1)]
