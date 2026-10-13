from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from latka_jazn.mcp.task_resume import McpTaskStore


def test_task_owner_is_persisted_and_isolation_survives_reopen(tmp_path: Path) -> None:
    store = McpTaskStore(tmp_path)
    task = store.create_or_get(
        daemon_request_id="req-v116-private", owner_subject="client/A",
        owner_transport="public_http",
    )
    assert task.owner_subject == "client/A"
    assert task.owner_transport == "public_http"
    assert task.authorization_revision == 1
    reopened = McpTaskStore(tmp_path)
    assert reopened.get(task.task_id, owner_subject="client/A", owner_transport="public_http")
    assert reopened.get(task.task_id, owner_subject="client/B", owner_transport="public_http") is None
    assert reopened.get(task.task_id, owner_subject="client/A", owner_transport="stdio") is None
    with pytest.raises(KeyError, match="unknown_task"):
        reopened.create_or_get(
            daemon_request_id="req-v116-private", owner_subject="client/B", owner_transport="public_http"
        )
    with pytest.raises(KeyError, match="unknown_task"):
        reopened.request_cancel(task.task_id, owner_subject="client/B", owner_transport="public_http")
    assert reopened.get(task.task_id, owner_subject="client/A", owner_transport="public_http").cancel_requested is False


def test_legacy_unowned_task_never_adopted_by_remote_caller(tmp_path: Path) -> None:
    store = McpTaskStore(tmp_path)
    task = store.create_or_get(daemon_request_id="req-v115-legacy")
    assert store.get(task.task_id, owner_subject="client/A", owner_transport="public_http") is None
    with pytest.raises(KeyError):
        store.create_or_get(
            daemon_request_id="req-v115-legacy", owner_subject="client/A", owner_transport="public_http"
        )
    with pytest.raises(KeyError):
        store.request_cancel(task.task_id, owner_subject="client/A", owner_transport="public_http")
    assert store.get(task.task_id).owner_subject is None


def test_existing_legacy_sqlite_schema_migrates_additively(tmp_path: Path) -> None:
    store = McpTaskStore(tmp_path)
    with sqlite3.connect(store.db_path) as conn:
        conn.execute("DROP TABLE mcp_tasks")
        conn.execute("""CREATE TABLE mcp_tasks (
            task_id TEXT PRIMARY KEY, daemon_request_id TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL, created_at TEXT NOT NULL, last_updated_at TEXT NOT NULL,
            ttl_ms INTEGER, poll_interval_ms INTEGER NOT NULL, result_json TEXT,
            error_json TEXT, status_message TEXT, request_id TEXT, turn_id TEXT,
            trace_id TEXT, host_request_contract_hash TEXT, input_requests_json TEXT,
            request_state TEXT, cancel_requested INTEGER NOT NULL DEFAULT 0,
            schema_version TEXT NOT NULL)""")
    migrated = McpTaskStore(tmp_path)
    with sqlite3.connect(migrated.db_path) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(mcp_tasks)")}
    assert {"owner_subject", "owner_transport", "authorization_revision"} <= columns
    assert migrated.create_or_get(daemon_request_id="after-migration").authorization_revision == 1


def test_incomplete_owner_fail_closed(tmp_path: Path) -> None:
    store = McpTaskStore(tmp_path)
    with pytest.raises(ValueError, match="task_owner_incomplete"):
        store.create_or_get(daemon_request_id="bad", owner_subject="client/A")
    with pytest.raises(ValueError, match="task_owner_invalid"):
        store.create_or_get(daemon_request_id="bad", owner_subject="", owner_transport="public_http")
