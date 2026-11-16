from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import sqlite3

from latka_jazn.audit.audit_context_store import sqlite_readonly_uri

from latka_jazn.runtime.candidate_decision_ledger import CandidateDecisionLedger
from latka_jazn.runtime.host_bridge_audit import HostBridgeAuditStore
from latka_jazn.runtime.idempotency import IdempotencyStore
from latka_jazn.version import schema_version

SCHEMA_VERSION = schema_version("cognitive_debugger")


@dataclass(slots=True)
class CognitiveDebugger:
    audit_database: Path

    def _local_runtime_events(self, turn_id: str, trace_id: str | None) -> list[dict[str, Any]]:
        """Read local Ollama/runtime evidence without exposing conversation payloads."""
        connection = sqlite3.connect(sqlite_readonly_uri(self.audit_database), uri=True, timeout=10.0)
        try:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA query_only=ON")
            tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_schema WHERE type='table'")}
            if "audit_runtime_events" not in tables:
                return []
            required = {"audit_event_id", "created_at_utc", "event_type", "source",
                        "trace_id", "turn_id", "payload_sha256"}
            columns = {row[1] for row in connection.execute("PRAGMA table_info(audit_runtime_events)")}
            if not required.issubset(columns):
                return []
            clause = " WHERE turn_id=?"
            params: tuple[Any, ...] = (turn_id,)
            if trace_id is not None:
                clause += " AND trace_id=?"
                params = (turn_id, trace_id)
            rows = connection.execute(
                "SELECT audit_event_id, created_at_utc, event_type, source, trace_id,"
                " turn_id, payload_sha256 FROM audit_runtime_events"
                + clause + " ORDER BY created_at_utc, audit_event_id LIMIT 256",
                params,
            ).fetchall()
            return [
                {
                    "source_table": "audit_runtime_events",
                    "audit_event_id": row["audit_event_id"],
                    "created_at_utc": row["created_at_utc"],
                    "event_type": row["event_type"],
                    "source": row["source"],
                    "turn_id": row["turn_id"],
                    "trace_id": row["trace_id"],
                    "payload_sha256": row["payload_sha256"],
                    "private_payload_redacted": True,
                }
                for row in rows
            ]
        finally:
            connection.close()

    def explain_turn(self, turn_id: str, *, trace_id: str | None = None, include_private: bool = False) -> dict[str, Any]:
        audits = HostBridgeAuditStore(self.audit_database).list_for_turn(turn_id, trace_id)
        local_events = self._local_runtime_events(turn_id, trace_id)
        decision_ids = {
            value
            for event in audits
            for value in [event.get("metadata", {}).get("decision_id")]
            if value
        }
        ledger = CandidateDecisionLedger(self.audit_database)
        decisions = [ledger.get(value, include_raw_text=include_private) for value in sorted(decision_ids)]
        decisions = [value for value in decisions if value is not None]
        return {
            "schema_version": SCHEMA_VERSION,
            "turn_id": turn_id,
            "trace_id": trace_id,
            "private_payloads_included": include_private,
            "timeline": sorted(
                [*audits, *local_events],
                key=lambda event: str(event.get("created_at_utc") or ""),
            ),
            "timeline_sources": {
                "host_bridge_audit": len(audits),
                "audit_runtime_events": len(local_events),
            },
            "local_event_limit": 256,
            "decisions": decisions,
            "truth_boundary": "Debugger reports persisted evidence; it is not an independent source of truth.",
        }

    def replay_turn(self, turn_id: str, *, trace_id: str | None = None, dry_run: bool = True) -> dict[str, Any]:
        explanation = self.explain_turn(turn_id, trace_id=trace_id, include_private=False)
        final_events = [
            event for event in explanation["timeline"] if event.get("event_type") in {"accept", "repair", "replay"}
        ]
        return {
            "schema_version": SCHEMA_VERSION,
            "turn_id": turn_id,
            "trace_id": trace_id,
            "dry_run": dry_run,
            "replayable": bool(final_events),
            "selected_event": final_events[-1] if final_events else None,
            "side_effects_performed": False,
        }
