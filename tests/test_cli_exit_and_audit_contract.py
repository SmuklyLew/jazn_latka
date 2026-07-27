from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from latka_jazn import cli
from latka_jazn.cli_commands import audit as audit_commands


def test_status_exit_code_tracks_confirmed_activity(monkeypatch, tmp_path: Path, capsys) -> None:
    monkeypatch.setattr(
        cli.diagnostics,
        "status_payload",
        lambda *_args, **_kwargs: {"ok": False, "daemon": {"active_state": "inactive_untrusted"}},
    )
    assert cli.main(["status", "--root", str(tmp_path), "--json"]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False


def test_restart_uses_final_status_not_stop_exit(monkeypatch, tmp_path: Path) -> None:
    exits = iter([1, 0])
    monkeypatch.setattr(cli, "_legacy_main", lambda _args: next(exits))
    monkeypatch.setattr(cli.diagnostics, "status_payload", lambda *_args, **_kwargs: {"ok": True})
    assert cli.main(["restart", "--root", str(tmp_path)]) == 0


def test_replay_execute_is_explicitly_rejected(monkeypatch, tmp_path: Path, capsys) -> None:
    monkeypatch.setattr(
        cli.audit_commands,
        "replay",
        lambda *_args, **kwargs: {
            "ok": False,
            "error_code": "replay_execution_not_implemented" if kwargs.get("execute") else None,
        },
    )
    assert cli.main([
        "replay-turn", "--root", str(tmp_path), "--turn-id", "turn-1", "--execute"
    ]) == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["error_code"] == "replay_execution_not_implemented"


def test_audit_tail_reads_both_tables_without_mutating_schema(tmp_path: Path) -> None:
    db = tmp_path / "audit.sqlite3"
    connection = sqlite3.connect(db)
    connection.executescript(
        """
        CREATE TABLE host_bridge_audit(
            audit_id INTEGER PRIMARY KEY,
            created_at_utc TEXT NOT NULL,
            metadata_json TEXT
        );
        CREATE TABLE audit_runtime_events(
            audit_event_id INTEGER PRIMARY KEY,
            created_at_utc TEXT NOT NULL,
            payload_json TEXT
        );
        INSERT INTO host_bridge_audit(created_at_utc, metadata_json)
        VALUES ('2026-07-27T10:00:00+00:00', '{"kind":"bridge"}');
        INSERT INTO audit_runtime_events(created_at_utc, payload_json)
        VALUES ('2026-07-27T11:00:00+00:00', '{"kind":"runtime"}');
        """
    )
    connection.commit()
    before_schema = connection.execute(
        "SELECT type,name,sql FROM sqlite_schema ORDER BY type,name"
    ).fetchall()
    connection.close()

    payload = audit_commands.audit_tail(db, 20)
    assert payload["ok"] is True
    assert {event["source_table"] for event in payload["events"]} == {
        "host_bridge_audit", "audit_runtime_events"
    }

    connection = sqlite3.connect(db)
    after_schema = connection.execute(
        "SELECT type,name,sql FROM sqlite_schema ORDER BY type,name"
    ).fetchall()
    connection.close()
    assert after_schema == before_schema


def test_audit_database_error_is_not_empty_success(tmp_path: Path) -> None:
    db = tmp_path / "audit.sqlite3"
    db.write_bytes(b"not sqlite")
    payload = audit_commands.audit_tail(db, 5)
    assert payload["ok"] is False
    assert payload["events"] == []
    assert payload["error_code"]
