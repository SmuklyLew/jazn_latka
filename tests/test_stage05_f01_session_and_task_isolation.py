"""F01: same client session identifier is not shared principal authority."""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

import pytest

from latka_jazn.config import JaznConfig
from latka_jazn.core import runtime_daemon as daemon
from latka_jazn.core.admission_owner_context import (
    AUTHENTICATED_HTTP_OWNER, admission_session_id, is_public_session_id, public_owner_digest,
)
from latka_jazn.core.runtime_session_state import RuntimeSessionState, RuntimeSessionStateStore
from latka_jazn.mcp import server_legacy_v76 as legacy
from latka_jazn.mcp.server import JaznMcpServer

ALICE = public_owner_digest("alice")
BOB = public_owner_digest("bob")


@contextmanager
def _server(root: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[daemon.JaznDaemonServer]:
    server = daemon.JaznDaemonServer(
        ("127.0.0.1", 0), daemon.JaznDaemonHandler,
        config=JaznConfig(root=root, memory_mode="off"),
        marker_path=daemon.resolve_active_runtime_marker_path(root),
        hard_worker_process_isolation=False,
    )
    monkeypatch.setattr(server, "start_chat_worker", lambda: None)
    monkeypatch.setattr(server, "start_chat_watchdog", lambda: None)
    try:
        yield server
    finally:
        server.close_sessions()
        server.server_close()


def _submit(server: daemon.JaznDaemonServer, request_id: str, owner: str | None,
            session_id: str | None = "same-client-session", *, reset: bool = False):
    return server.submit_chat_job(
        request_id=request_id, user_text="synthetic", session_id=session_id,
        input_field="message", no_carryover=False, client="synthetic",
        admission_owner_sha256=owner, reset_session=reset,
    )


def test_canonical_admission_partitions_worker_and_gate_keys_across_restart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    with _server(tmp_path, monkeypatch) as first:
        a, created, error = _submit(first, "a1", ALICE)
        assert a is not None and created and error is None
        b, created, error = _submit(first, "b1", BOB, reset=True)
        assert b is not None and created and error is None
        local, created, error = _submit(first, "local1", None)
        assert local is not None and created and error is None
        assert a.session_id is not None and b.session_id is not None
        assert is_public_session_id(a.session_id) and is_public_session_id(b.session_id)
        assert len({a.session_id, b.session_id, local.session_id}) == 3
        assert local.session_id == "same-client-session"
        assert a.turn_context is not None and a.turn_context.session_id == a.session_id
        for owner in (None, BOB, ALICE):
            job, created, error = _submit(first, "forbidden-" + str(owner), owner, a.session_id)
            assert job is None and not created and error is not None
            assert error["error_code"] == "reserved_public_session_id"
        a_key = a.session_id
        b_key = b.session_id
        assert first._chat_queue.qsize() == 3
    with _server(tmp_path, monkeypatch) as reopened:
        same, created, error = _submit(reopened, "a1", ALICE)
        assert same is not None and not created and error is None and same.session_id == a_key
        following, created, error = _submit(reopened, "a2", ALICE)
        assert following is not None and created and error is None and following.session_id == a_key
        other, created, error = _submit(reopened, "b2", BOB)
        assert other is not None and created and error is None and other.session_id == b_key


def test_implicit_public_session_is_per_request_and_reserved_namespace_is_casefolded() -> None:
    first = admission_session_id(None, request_id="r", owner_sha256=ALICE)
    assert first == admission_session_id(None, request_id="r", owner_sha256=ALICE)
    assert first != admission_session_id(None, request_id="r", owner_sha256=BOB)
    assert first != admission_session_id(None, request_id="s", owner_sha256=ALICE)
    assert first != admission_session_id("r", request_id="r", owner_sha256=ALICE)
    assert admission_session_id(None, request_id="r", owner_sha256=None) is None
    assert first is not None
    with pytest.raises(ValueError, match="reserved_public_session_id"):
        admission_session_id(first.upper(), request_id="r", owner_sha256=None)


def test_scoped_checkpoint_never_publishes_to_unscoped_latest(
    tmp_path: Path,
) -> None:
    a_key = admission_session_id("shared", request_id="a", owner_sha256=ALICE)
    b_key = admission_session_id("shared", request_id="b", owner_sha256=BOB)
    assert a_key is not None and b_key is not None
    local_store = RuntimeSessionStateStore(tmp_path)
    local_state = local_store.load_or_create(session_id="local")
    local_state.update(user_text="local-canary")
    assert local_store.save(local_state)["session_state_saved"] is True
    latest_before = local_store.latest_path.read_bytes()
    a_store = RuntimeSessionStateStore(tmp_path)
    a_state = a_store.load_or_create(session_id=a_key)
    a_state.update(user_text="alice-canary", visible_text="alice-response")
    saved = a_store.save(a_state)
    assert saved["session_state_saved"] is True
    assert saved["latest_session_pointer_required"] is False
    assert local_store.latest_path.read_bytes() == latest_before
    assert RuntimeSessionStateStore(tmp_path).load_or_create(session_id=b_key).last_user_text is None
    assert RuntimeSessionStateStore(tmp_path).load_or_create(session_id=a_key).last_user_text == "alice-canary"
    assert RuntimeSessionStateStore(tmp_path).load_or_create().last_user_text == "local-canary"
    # Historical/misplaced pointer remains on disk, but cannot confer authority.
    local_store.latest_path.write_bytes(a_store.path.read_bytes())
    unscoped = RuntimeSessionStateStore(tmp_path).load_or_create()
    assert unscoped.session_id != a_key and unscoped.last_user_text is None


@pytest.mark.parametrize("method", ["tasks/get", "tasks/cancel", "tasks/update"])
def test_legacy_task_protocol_rejects_foreign_and_ownerless_caller(
    tmp_path: Path, method: str, stage05_public_context: Any,
) -> None:
    stage05_public_context(tmp_path, "alice", "owned-request")
    server = JaznMcpServer(root=tmp_path, allow_unauthenticated_local_test=True)
    task = server.task_resume.store.create_or_get(
        daemon_request_id="owned-request", owner_subject="alice", owner_transport="public_http",
    )
    server.task_resume.store.update(task.task_id, status="completed", result={"canary": "alice-private"})
    request = {"jsonrpc": "2.0", "id": 1, "method": method,
               "params": {"taskId": task.task_id, "inputResponses": {},
                          "_meta": {"subject": "alice", "openai/subject": "alice"}}}
    for subject in (None, "bob"):
        token = AUTHENTICATED_HTTP_OWNER.set(subject)
        try:
            denied = legacy.JaznMcpServer.handle(server, request)
        finally:
            AUTHENTICATED_HTTP_OWNER.reset(token)
        assert denied is not None and "error" in denied
        assert "alice-private" not in repr(denied)
    if method == "tasks/get":
        token = AUTHENTICATED_HTTP_OWNER.set("alice")
        try:
            allowed = legacy.JaznMcpServer.handle(server, request)
        finally:
            AUTHENTICATED_HTTP_OWNER.reset(token)
        assert allowed is not None and allowed["result"]["result"]["canary"] == "alice-private"
    persisted = server.task_resume.store.get(task.task_id)
    assert persisted is not None and persisted.cancel_requested is False


def test_legacy_task_creation_uses_verified_principal_not_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stage05_public_context: Any,
) -> None:
    stage05_public_context(tmp_path, "alice", "owned-r")
    server = JaznMcpServer(root=tmp_path, allow_unauthenticated_local_test=True)
    pending = {"structuredContent": {"action": "poll_runtime", "daemon_request_id": "owned-r"}}
    def call_tool(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return pending
    monkeypatch.setattr(server, "call_tool", call_tool)
    request = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
               "params": {"name": "jazn_generate_visible_reply", "arguments": {},
                          "_meta": {"subject": "bob", "io.modelcontextprotocol/clientCapabilities":
                                    {"extensions": {legacy.TASK_EXTENSION_ID: {}}}}}}
    token = AUTHENTICATED_HTTP_OWNER.set("alice")
    try:
        result = legacy.JaznMcpServer.handle(server, request)
    finally:
        AUTHENTICATED_HTTP_OWNER.reset(token)
    assert result is not None and "result" in result
    task_id = result["result"]["taskId"]
    assert server.task_resume.store.get(task_id, owner_subject="alice", owner_transport="public_http") is not None
    assert server.task_resume.store.get(task_id, owner_subject="bob", owner_transport="public_http") is None
    with pytest.raises(KeyError, match="unknown_task"):
        server.task_resume.create_from_pending_result(pending)
