"""Read-only metadata diagnostics for a local Ollama runtime turn."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from latka_jazn.core.cognitive_debugger import CognitiveDebugger


def test_explain_turn_includes_only_redacted_local_audit_metadata(tmp_path: Path) -> None:
    db = tmp_path / "audit.sqlite3"
    connection = sqlite3.connect(db)
    connection.executescript(
        """
        CREATE TABLE audit_runtime_events(
            audit_event_id TEXT PRIMARY KEY,
            created_at_utc TEXT NOT NULL,
            event_type TEXT NOT NULL,
            source TEXT NOT NULL,
            actor TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            tags_json TEXT NOT NULL,
            trace_id TEXT,
            turn_id TEXT,
            payload_sha256 TEXT NOT NULL
        );
        INSERT INTO audit_runtime_events VALUES(
            'evt1','2026-11-16T15:00:00+00:00','runtime_turn_completed',
            'runtime','system','{"secret":"SYNTHETIC_PRIVATE_VALUE"}','[]',
            'trace1','turn1','hash1'
        );
        INSERT INTO audit_runtime_events VALUES(
            'evt2','2026-11-16T15:01:00+00:00','runtime_turn_completed',
            'runtime','system','{"secret":"other"}','[]',
            'trace2','turn2','hash2'
        );
        """
    )
    before = connection.execute("SELECT COUNT(*) FROM audit_runtime_events").fetchone()[0]
    connection.commit()
    connection.close()

    report = CognitiveDebugger(db).explain_turn("turn1")
    assert report["timeline_sources"] == {"host_bridge_audit": 0, "audit_runtime_events": 1}
    assert len(report["timeline"]) == 1
    assert report["timeline"][0]["event_type"] == "runtime_turn_completed"
    assert report["timeline"][0]["private_payload_redacted"] is True
    assert "SYNTHETIC_PRIVATE_VALUE" not in json.dumps(report)
    assert "payload_json" not in report["timeline"][0]
    assert CognitiveDebugger(db).explain_turn("turn1", trace_id="wrong")["timeline"] == []

    with sqlite3.connect(db) as verify:
        assert verify.execute("SELECT COUNT(*) FROM audit_runtime_events").fetchone()[0] == before


def test_explain_turn_reports_absent_local_audit_table_without_fake_evidence(tmp_path: Path) -> None:
    db = tmp_path / "audit.sqlite3"
    with sqlite3.connect(db) as connection:
        connection.execute("CREATE TABLE unrelated(data TEXT)")
    report = CognitiveDebugger(db).explain_turn("missing")
    assert report["timeline"] == []
    assert report["timeline_sources"]["audit_runtime_events"] == 0
