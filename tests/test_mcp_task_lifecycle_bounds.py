from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

from latka_jazn.mcp.task_resume import McpTaskResumeAdapter, McpTaskStore


class _UnusedGateway:
    def result(self, request_id: str) -> dict[str, Any]:
        raise AssertionError(f"runtime must not be polled for {request_id}")


def _age_task(store: McpTaskStore, task_id: str, *, seconds: float) -> None:
    created = (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat()
    with sqlite3.connect(store.db_path) as conn:
        conn.execute(
            "UPDATE mcp_tasks SET created_at = ?, last_updated_at = ? WHERE task_id = ?",
            (created, created, task_id),
        )


def test_tasks_get_enforces_advertised_ttl_without_polling_runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = McpTaskResumeAdapter(root=tmp_path, gateway=_UnusedGateway(), ttl_ms=1_000)
    task = adapter.store.create_or_get(
        daemon_request_id="req-expired-task",
        ttl_ms=1_000,
    )
    _age_task(adapter.store, task.task_id, seconds=5)

    def unexpected_resume(**_kwargs: Any) -> dict[str, Any]:
        raise AssertionError("expired task must fail before runtime polling")

    monkeypatch.setattr(
        "latka_jazn.mcp.task_resume.jazn_resume_visible_reply.run",
        unexpected_resume,
    )
    result = adapter.get(task.task_id)

    assert result["status"] == "failed"
    assert result["error"]["code"] == -32603
    assert result["error"]["message"] == "task_ttl_elapsed"


def test_tasks_get_repeats_input_required_snapshot_without_runtime_reentry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = McpTaskResumeAdapter(root=tmp_path, gateway=_UnusedGateway())
    task = adapter.store.create_or_get(daemon_request_id="req-input-snapshot")
    adapter.store.update(
        task.task_id,
        status="input_required",
        input_requests={"confirm": {"method": "elicitation/create", "params": {"message": "Continue?"}}},
        request_state="state-1",
        status_message="Client input required.",
    )

    def unexpected_resume(**_kwargs: Any) -> dict[str, Any]:
        raise AssertionError("input_required task must not re-enter runtime")

    monkeypatch.setattr(
        "latka_jazn.mcp.task_resume.jazn_resume_visible_reply.run",
        unexpected_resume,
    )
    first = adapter.get(task.task_id)
    second = adapter.get(task.task_id)

    assert first == second
    assert first["status"] == "input_required"
    assert first["requestState"] == "state-1"
    assert first["inputRequests"]["confirm"]["method"] == "elicitation/create"


def test_unexpected_poll_failure_does_not_expose_exception_text(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = McpTaskResumeAdapter(root=tmp_path, gateway=_UnusedGateway())
    task = adapter.store.create_or_get(daemon_request_id="req-redacted-error")

    def fail_with_sensitive_detail(**_kwargs: Any) -> dict[str, Any]:
        raise RuntimeError("secret-token-and-local-path-must-not-leak")

    monkeypatch.setattr(
        "latka_jazn.mcp.task_resume.jazn_resume_visible_reply.run",
        fail_with_sensitive_detail,
    )
    result = adapter.get(task.task_id)
    encoded = str(result)

    assert result["status"] == "failed"
    assert result["error"]["message"] == "task_poll_failed:RuntimeError"
    assert "secret-token-and-local-path-must-not-leak" not in encoded


def test_same_daemon_request_is_idempotent_across_independent_stores(
    tmp_path: Path,
) -> None:
    def create() -> str:
        return McpTaskStore(tmp_path).create_or_get(
            daemon_request_id="req-cross-process-idempotent"
        ).task_id

    with ThreadPoolExecutor(max_workers=8) as pool:
        task_ids = list(pool.map(lambda _index: create(), range(24)))

    assert len(set(task_ids)) == 1
    store = McpTaskStore(tmp_path)
    with sqlite3.connect(store.db_path) as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM mcp_tasks WHERE daemon_request_id = ?",
            ("req-cross-process-idempotent",),
        ).fetchone()[0] == 1


def test_cancel_intent_is_idempotent_and_terminal_state_is_not_reopened(
    tmp_path: Path,
) -> None:
    store = McpTaskStore(tmp_path)
    task = store.create_or_get(daemon_request_id="req-cancel-atomic")

    first = store.request_cancel(task.task_id)
    second = McpTaskStore(tmp_path).request_cancel(task.task_id)
    assert first.cancel_requested is True
    assert second.cancel_requested is True
    assert second.status == "working"

    completed = store.update(
        task.task_id,
        status="completed",
        result={"content": [{"type": "text", "text": "done"}]},
    )
    after_terminal_cancel = McpTaskStore(tmp_path).request_cancel(task.task_id)

    assert completed.status == "completed"
    assert after_terminal_cancel.status == "completed"
    assert after_terminal_cancel.cancel_requested is True


def test_negative_task_ttl_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="task_ttl_must_be_non_negative_or_none"):
        McpTaskStore(tmp_path).create_or_get(
            daemon_request_id="req-negative-ttl",
            ttl_ms=-1,
        )
