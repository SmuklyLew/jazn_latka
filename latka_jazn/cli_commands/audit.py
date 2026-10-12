from __future__ import annotations

from pathlib import Path
from typing import Any
import json
import sqlite3

from latka_jazn.audit.audit_context_store import sqlite_readonly_uri
from latka_jazn.core.cognitive_debugger import CognitiveDebugger


def _decode_json_fields(item: dict[str, Any]) -> dict[str, Any]:
    for source, target in (("metadata_json", "metadata"), ("payload_json", "payload"), ("tags_json", "tags")):
        raw = item.pop(source, None)
        if raw is not None:
            try:
                item[target] = json.loads(raw)
            except (TypeError, json.JSONDecodeError):
                item[target] = None
                item[f"{target}_decode_error"] = True
    return item


def audit_tail(path: Path, limit: int = 20) -> dict[str, Any]:
    if not path.is_file():
        return {
            "ok": False,
            "events": [],
            "database": str(path),
            "exists": False,
            "error_code": "audit_database_missing",
        }
    connection: sqlite3.Connection | None = None
    try:
        connection = sqlite3.connect(sqlite_readonly_uri(path), uri=True, timeout=10.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_schema WHERE type='table'")}
        events: list[dict[str, Any]] = []
        selected_tables: list[str] = []
        size = max(0, int(limit))
        if "host_bridge_audit" in tables:
            selected_tables.append("host_bridge_audit")
            rows = connection.execute(
                "SELECT * FROM host_bridge_audit ORDER BY created_at_utc DESC,audit_id DESC LIMIT ?",
                (size,),
            ).fetchall()
            for row in rows:
                item = _decode_json_fields(dict(row))
                item["source_table"] = "host_bridge_audit"
                events.append(item)
        if "audit_runtime_events" in tables:
            selected_tables.append("audit_runtime_events")
            rows = connection.execute(
                "SELECT * FROM audit_runtime_events ORDER BY created_at_utc DESC,audit_event_id DESC LIMIT ?",
                (size,),
            ).fetchall()
            for row in rows:
                item = _decode_json_fields(dict(row))
                item["source_table"] = "audit_runtime_events"
                events.append(item)
        events.sort(key=lambda item: str(item.get("created_at_utc") or ""), reverse=True)
        return {
            "ok": True,
            "events": events[:size],
            "database": str(path),
            "exists": True,
            "tables_detected": sorted(tables),
            "event_tables": selected_tables,
            "error_code": None,
        }
    except (sqlite3.DatabaseError, OSError) as exc:
        return {
            "ok": False,
            "events": [],
            "database": str(path),
            "exists": path.exists(),
            "error_code": type(exc).__name__,
            "error": str(exc),
        }
    finally:
        if connection is not None:
            connection.close()


def explain(path: Path, turn_id: str, trace_id: str | None = None) -> dict[str, Any]:
    if not path.is_file():
        return {"ok": False, "error_code": "audit_database_missing", "database": str(path)}
    try:
        payload = CognitiveDebugger(path).explain_turn(turn_id, trace_id=trace_id, include_private=False)
        return {"ok": True, **payload, "error_code": None}
    except (sqlite3.DatabaseError, OSError, FileNotFoundError) as exc:
        return {"ok": False, "error_code": type(exc).__name__, "error": str(exc), "database": str(path)}


def replay(path: Path, turn_id: str, trace_id: str | None = None, *, execute: bool = False) -> dict[str, Any]:
    if execute:
        return {
            "ok": False,
            "error_code": "replay_execution_not_implemented",
            "side_effects_performed": False,
            "turn_id": turn_id,
            "trace_id": trace_id,
        }
    payload = explain(path, turn_id, trace_id)
    if not payload.get("ok"):
        return payload
    replay_payload = CognitiveDebugger(path).replay_turn(turn_id, trace_id=trace_id, dry_run=True)
    return {"ok": True, **replay_payload, "error_code": None}
