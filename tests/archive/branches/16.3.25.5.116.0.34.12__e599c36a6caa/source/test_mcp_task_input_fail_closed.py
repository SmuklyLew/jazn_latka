from __future__ import annotations

from pathlib import Path

import pytest

from latka_jazn.mcp.task_resume import McpTaskResumeAdapter


class _UnusedGateway:
    def result(self, request_id: str):
        raise AssertionError(request_id)


def test_task_input_update_never_mutates_outstanding_requests_without_runtime_transport(
    tmp_path: Path,
) -> None:
    adapter = McpTaskResumeAdapter(root=tmp_path, gateway=_UnusedGateway())
    task = adapter.store.create_or_get(daemon_request_id="req-input-fail-closed")
    adapter.store.update(
        task.task_id,
        status="input_required",
        input_requests={
            "first": {"method": "elicitation/create", "params": {"message": "one"}},
            "second": {"method": "elicitation/create", "params": {"message": "two"}},
        },
        request_state="waiting",
    )

    with pytest.raises(
        RuntimeError,
        match="task_input_runtime_transport_not_implemented",
    ):
        adapter.update_input(task.task_id, {"first": {"value": "answer"}})

    persisted = adapter.store.get(task.task_id)
    assert persisted is not None
    assert persisted.status == "input_required"
    assert persisted.input_requests == {
        "first": {"method": "elicitation/create", "params": {"message": "one"}},
        "second": {"method": "elicitation/create", "params": {"message": "two"}},
    }
    assert persisted.request_state == "waiting"


def test_task_update_outside_input_required_is_ack_only_and_does_not_rewrite_state(
    tmp_path: Path,
) -> None:
    adapter = McpTaskResumeAdapter(root=tmp_path, gateway=_UnusedGateway())
    task = adapter.store.create_or_get(daemon_request_id="req-input-noop")

    result = adapter.update_input(task.task_id, {"unused": {"value": True}})

    assert result == {"resultType": "complete"}
    persisted = adapter.store.get(task.task_id)
    assert persisted is not None
    assert persisted.status == "working"
    assert persisted.input_requests is None
