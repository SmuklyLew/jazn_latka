"""F01: shared private engine context requires an explicit reviewed owner."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from latka_jazn.config import JaznConfig
from latka_jazn.core import runtime_daemon as daemon
from latka_jazn.core.admission_owner_context import (
    PRIVATE_CONTEXT_OWNER_FILE, current_admission_owner, public_owner_digest, public_private_context_authorized,
)
from latka_jazn.mcp.server import JaznMcpServer
from latka_jazn.mcp.task_resume import McpTaskStore, McpTaskResumeAdapter
from latka_jazn.mcp.tools import jazn_resume_visible_reply as resume

ALICE = public_owner_digest("alice")
BOB = public_owner_digest("bob")


@pytest.mark.parametrize("damage", ["missing", "malformed", "unreviewed", "foreign", "extra", "valid"])
def test_private_context_policy_never_claims_or_rewrites_data(
    tmp_path: Path, stage05_public_context: Any, damage: str,
) -> None:
    path = tmp_path / PRIVATE_CONTEXT_OWNER_FILE
    if damage != "missing":
        stage05_public_context(tmp_path, "alice", None)
        payload = json.loads(path.read_text(encoding="utf-8"))
        if damage == "malformed":
            path.write_text("{", encoding="utf-8")
        elif damage == "unreviewed":
            payload["existing_shared_context_reviewed"] = False
            path.write_text(json.dumps(payload), encoding="utf-8")
        elif damage == "foreign":
            payload["owner_sha256"] = BOB
            path.write_text(json.dumps(payload), encoding="utf-8")
        elif damage == "extra":
            payload["extra"] = True
            path.write_text(json.dumps(payload), encoding="utf-8")
    before = path.read_bytes() if path.exists() else None
    assert public_private_context_authorized(tmp_path, ALICE) == (damage == "valid")
    if damage != "foreign":
        assert not public_private_context_authorized(tmp_path, BOB)
    assert (path.read_bytes() if path.exists() else None) == before


@pytest.mark.parametrize("memory_mode", ["off", "optional"])
def test_foreign_admission_never_reaches_worker_or_shared_context(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stage05_public_context: Any, memory_mode: str,
) -> None:
    stage05_public_context(tmp_path, "alice", None)
    server = daemon.JaznDaemonServer(
        ("127.0.0.1", 0), daemon.JaznDaemonHandler,
        config=JaznConfig(root=tmp_path, memory_mode=memory_mode),
        marker_path=daemon.resolve_active_runtime_marker_path(tmp_path),
        hard_worker_process_isolation=False,
    )
    monkeypatch.setattr(server, "start_chat_worker", lambda: None)
    monkeypatch.setattr(server, "start_chat_watchdog", lambda: None)
    def forbidden(*_args: Any, **_kwargs: Any) -> Any:
        pytest.fail("foreign principal reached worker construction / shared memory")
    monkeypatch.setattr(server, "get_session", forbidden)
    try:
        job, created, error = server.submit_chat_job(
            request_id="bob-r", user_text="synthetic", session_id="shared",
            input_field="message", no_carryover=False, client="synthetic",
            admission_owner_sha256=BOB, reset_session=True,
        )
        assert job is not None and created and error is None
        server._process_chat_job(job)
        assert job.status == "failed" and job.result is not None
        assert job.result["error_code"] == "daemon_session_private_context_owner_unverified"
        assert not server.sessions
        with pytest.raises(PermissionError, match="public_private_context_owner_unverified"):
            server.get_chat_job("bob-r", admission_owner_sha256=BOB)
    finally:
        server.close_sessions()
        server.server_close()


def test_public_ingress_denies_before_any_private_dispatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stage05_public_context: Any,
) -> None:
    stage05_public_context(tmp_path, "alice", None)
    server = JaznMcpServer(root=tmp_path, token="synthetic-token")
    def forbidden(*_args: Any, **_kwargs: Any) -> Any:
        pytest.fail("private dispatch reached without authorization")
    monkeypatch.setattr(server, "_dispatch", forbidden)
    monkeypatch.setattr(server, "_authorize_public_turn_resource", forbidden)
    for name, args in (
        ("jazn_generate_visible_reply", {"request_id": "bob-r", "message": "synthetic"}),
        ("jazn_resume_visible_reply", {"daemon_request_id": "bob-r"}),
        ("jazn_finalize_reply", {"continuation_token": "synthetic", "final_text": "synthetic",
                                "final_text_sha256": "0" * 64}),
    ):
        result = server.call_public_authenticated(name, args, owner_subject="bob",
                                                  meta={"authorization": "synthetic-token", "subject": "bob"})
        assert result["isError"] is True
        assert "public_private_context_owner_unverified" in repr(result)


@pytest.mark.parametrize("case", ["missing", "foreign_admission", "valid", "revoked"])
def test_task_result_requires_canonical_owner_and_reviewed_context(
    tmp_path: Path, stage05_public_context: Any, case: str,
) -> None:
    if case == "foreign_admission":
        stage05_public_context(tmp_path, "bob", "task-r")
        stage05_public_context(tmp_path, "alice", None)
    else:
        stage05_public_context(tmp_path, "alice", "task-r" if case != "missing" else None)
    store = McpTaskStore(tmp_path)
    task = store.create_or_get(daemon_request_id="task-r", owner_subject="alice", owner_transport="public_http")
    store.update(task.task_id, status="completed", result={"canary": "private-alice"})
    if case == "revoked":
        (tmp_path / PRIVATE_CONTEXT_OWNER_FILE).unlink()
    reopened = McpTaskStore(tmp_path)
    visible = reopened.get_protocol_record(task.task_id, owner_subject="alice", owner_transport="public_http")
    assert (visible is not None) == (case == "valid")
    if visible is not None:
        assert visible.to_task_result()["result"]["canary"] == "private-alice"
    assert reopened.get_protocol_record(task.task_id, owner_subject="bob", owner_transport="public_http") is None
    assert reopened.get_protocol_record(task.task_id) is None
    assert reopened.get(task.task_id) is not None  # explicit operator seam retained


def test_public_task_poll_uses_public_recovery_not_internal_seam(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stage05_public_context: Any,
) -> None:
    stage05_public_context(tmp_path, "alice", "task-r")
    class Gateway:
        def result(self, request_id: str) -> dict[str, Any]:
            pytest.fail("unexpected direct poll")
    adapter = McpTaskResumeAdapter(root=tmp_path, gateway=Gateway(), daemon_url="http://127.0.0.1:8787")
    task = adapter.store.create_or_get(
        daemon_request_id="task-r", owner_subject="alice", owner_transport="public_http",
        turn_id="t", host_request_contract_hash="a" * 64,
    )
    def internal(*_args: Any, **_kwargs: Any) -> Any:
        pytest.fail("public task used internal recovery")
    def public(**kwargs: Any) -> dict[str, Any]:
        assert current_admission_owner() == ALICE
        assert kwargs["daemon_request_id"] == "task-r"
        assert kwargs["turn_id"] == "t" and kwargs["host_request_contract_hash"] == "a" * 64
        assert kwargs["daemon_url"] == "http://127.0.0.1:8787"
        return {"structuredContent": {"action": "poll_runtime"}, "isError": False}
    monkeypatch.setattr(resume, "run", internal)
    monkeypatch.setattr(resume, "run_public", public)
    assert adapter.get(task.task_id, owner_subject="alice", owner_transport="public_http")["status"] == "working"
    assert current_admission_owner() is None
