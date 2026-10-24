"""Supplied independent pins must not be diagnosed as absent."""
from pathlib import Path

from latka_jazn.tools.memory_rebuild_app.p1_active_memory_readiness import assess_active_memory_readiness
from latka_jazn.tools.memory_rebuild_app.p1_provenance_chain import PinnedMemoryArtifact


def test_present_pin_with_no_runtime_reports_the_actual_missing_gate(tmp_path: Path) -> None:
    report = assess_active_memory_readiness(tmp_path,
        pinned_reference=PinnedMemoryArtifact(tmp_path / "synthetic-reference.sqlite3", "a" * 64))
    assert report["runtime_ready"] is False
    assert report["checks"]["provenance"]["state"] == "unverified"
    assert report["checks"]["provenance"]["issue"] == "runtime_not_ready_for_pinned_provenance"
    assert report["activation_authorized"] is False
    assert list(tmp_path.iterdir()) == []
