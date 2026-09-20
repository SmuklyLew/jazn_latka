from __future__ import annotations

import sqlite3
from pathlib import Path

from latka_jazn.mcp.task_resume import McpTaskStore


def test_v81_task_registry_is_sqlite_durable_and_idempotent(tmp_path: Path) -> None:
    first_store = McpTaskStore(tmp_path)
    first = first_store.create_or_get(
        daemon_request_id="req-v81-durable",
        request_id="req-v81-durable",
        turn_id="turn-v81",
        trace_id="trace-v81",
        host_request_contract_hash="a" * 64,
    )

    reopened = McpTaskStore(tmp_path)
    second = reopened.create_or_get(daemon_request_id="req-v81-durable")

    assert second.task_id == first.task_id
    assert second.lineage()["request_id"] == "req-v81-durable"
    assert second.lineage()["turn_id"] == "turn-v81"
    assert reopened.db_path.name == "mcp_tasks.sqlite3"
    with sqlite3.connect(reopened.db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM mcp_tasks").fetchone()[0] == 1


def test_v81_task_cancel_is_intent_until_runtime_acknowledges(tmp_path: Path) -> None:
    store = McpTaskStore(tmp_path)
    task = store.create_or_get(daemon_request_id="req-v81-cancel")
    updated = store.request_cancel(task.task_id)

    assert updated.status == "working"
    assert updated.cancel_requested is True
    assert "no verified cancellation acknowledgement" in str(updated.status_message)


def test_v81_task_registry_survives_new_store_instance(tmp_path: Path) -> None:
    task = McpTaskStore(tmp_path).create_or_get(daemon_request_id="req-v81-reopen")
    reopened = McpTaskStore(tmp_path).get(task.task_id)

    assert reopened is not None
    assert reopened.daemon_request_id == "req-v81-reopen"
    assert reopened.status == "working"
