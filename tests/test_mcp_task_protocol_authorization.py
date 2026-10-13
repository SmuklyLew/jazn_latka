from __future__ import annotations

from pathlib import Path

from latka_jazn.mcp.server import (
    JaznMcpServer, MCP_PROTOCOL_VERSION_MODERN,
    META_PROTOCOL_VERSION, META_CLIENT_CAPABILITIES, TASK_EXTENSION_ID,
)


def _request(method: str, task_id: str, *, subject: str, marker: bool = True) -> dict:
    meta = {
        META_PROTOCOL_VERSION: MCP_PROTOCOL_VERSION_MODERN,
        META_CLIENT_CAPABILITIES: {"extensions": {TASK_EXTENSION_ID: {}}},
        "subject": subject,
        "openai/subject": subject,
    }
    if marker:
        meta["jazn/authenticated_transport"] = "public_http"
    return {"jsonrpc": "2.0", "id": 9, "method": method,
            "params": {"taskId": task_id, "_meta": meta}}


def test_mcp_tasks_get_and_cancel_reject_unrelated_authenticated_subject(tmp_path: Path) -> None:
    server = JaznMcpServer(root=tmp_path, allow_unauthenticated_local_test=True)
    task = server.task_resume.store.create_or_get(
        daemon_request_id="request-private-http", owner_subject="alice", owner_transport="public_http"
    )
    for method in ("tasks/get", "tasks/cancel"):
        denied = server.handle_public_authenticated(_request(method, task.task_id, subject="bob"), owner_subject="bob", owner_transport="public_http")
        assert denied is not None
        assert denied.get("error", {}).get("message") == "Unknown taskId"
    persisted = server.task_resume.store.get(task.task_id)
    assert persisted is not None
    assert persisted.cancel_requested is False


def test_mcp_tasks_get_accepts_matching_authenticated_subject(tmp_path: Path) -> None:
    server = JaznMcpServer(root=tmp_path, allow_unauthenticated_local_test=True)
    task = server.task_resume.store.create_or_get(
        daemon_request_id="request-finished-http", owner_subject="alice", owner_transport="public_http"
    )
    server.task_resume.store.update(task.task_id, status="completed", result={"ok": True})
    visible = server.handle_public_authenticated(_request("tasks/get", task.task_id, subject="alice"), owner_subject="alice", owner_transport="public_http")
    assert visible is not None
    assert visible.get("result", {}).get("taskId") == task.task_id
    assert visible["result"]["status"] == "completed"


def test_legacy_unowned_task_cannot_be_read_via_public_http(tmp_path: Path) -> None:
    server = JaznMcpServer(root=tmp_path, allow_unauthenticated_local_test=True)
    task = server.task_resume.store.create_or_get(daemon_request_id="request-legacy-unknown")
    denied = server.handle_public_authenticated(_request("tasks/get", task.task_id, subject="alice"), owner_subject="alice", owner_transport="public_http")
    assert denied is not None
    assert denied.get("error", {}).get("message") == "Unknown taskId"

def test_spoofed_client_metadata_does_not_grant_task_ownership(tmp_path: Path) -> None:
    server = JaznMcpServer(root=tmp_path, allow_unauthenticated_local_test=True)
    task = server.task_resume.store.create_or_get(
        daemon_request_id="request-owned-spoof", owner_subject="alice", owner_transport="public_http"
    )
    forged = server.handle(_request("tasks/get", task.task_id, subject="alice"))
    assert forged is not None
    assert forged.get("error", {}).get("message") == "Unknown taskId"
