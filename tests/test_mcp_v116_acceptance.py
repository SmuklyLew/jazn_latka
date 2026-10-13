from __future__ import annotations

from pathlib import Path
import pytest

from latka_jazn.mcp.task_resume import McpTaskResumeAdapter


class RuntimeReceiptGateway:
    def __init__(self) -> None:
        self.accepted = True
        self.deliveries: list[dict] = []

    def result(self, request_id: str) -> dict:
        raise AssertionError("must never replay a turn")

    def submit_task_input(self, **kwargs):
        self.deliveries.append(kwargs)
        return {
            "accepted": self.accepted,
            "daemon_request_id": kwargs["daemon_request_id"],
            "task_id": kwargs["task_id"],
            "input_sha256": kwargs["input_sha256"],
            "accepted_keys": list(kwargs["input_responses"]),
        }


def test_mcp_task_input_end_to_end_receipt_and_fail_closed(tmp_path: Path) -> None:
    runtime = RuntimeReceiptGateway()
    adapter = McpTaskResumeAdapter(root=tmp_path, gateway=runtime)
    task = adapter.store.create_or_get(
        daemon_request_id="request-1", request_id="request-1", turn_id="turn-1",
        owner_subject="alice", owner_transport="public_http",
    )
    adapter.store.update(
        task.task_id, status="input_required",
        input_requests={"a": {}, "b": {}}, request_state="opaque",
    )
    with pytest.raises(KeyError):
        adapter.update_input(
            task.task_id, {"a": {"value": 1}},
            owner_subject="bob", owner_transport="public_http",
        )
    with pytest.raises(ValueError, match="not_outstanding"):
        adapter.update_input(
            task.task_id, {"x": {}},
            owner_subject="alice", owner_transport="public_http",
        )
    runtime.accepted = False
    with pytest.raises(RuntimeError, match="ack_unverified"):
        adapter.update_input(
            task.task_id, {"a": {"value": 1}},
            owner_subject="alice", owner_transport="public_http",
        )
    assert adapter.store.get(task.task_id).input_requests == {"a": {}, "b": {}}
    runtime.accepted = True
    assert adapter.update_input(
        task.task_id, {"a": {"value": 1}},
        owner_subject="alice", owner_transport="public_http",
    ) == {"resultType": "complete"}
    waiting = adapter.store.get(task.task_id)
    assert waiting is not None and waiting.status == "input_required" and waiting.input_requests == {"b": {}}
    assert adapter.update_input(
        task.task_id, {"b": {"value": 2}},
        owner_subject="alice", owner_transport="public_http",
    ) == {"resultType": "complete"}
    finished = adapter.store.get(task.task_id)
    assert finished is not None and finished.status == "working" and finished.input_requests is None
    assert all(
        d["daemon_request_id"] == "request-1" and d["lineage"]["turn_id"] == "turn-1"
        for d in runtime.deliveries
    )
