"""F01: authenticated principal is bound across real loopback admission/poll."""
from __future__ import annotations

from contextlib import contextmanager
import http.client
import json
from pathlib import Path
import threading
from typing import Any, Iterator

import pytest

from latka_jazn.bridge.secure_host_runtime_gateway import (
    GatewayConfig, GatewayError, SecureHostRuntimeGateway,
)
from latka_jazn.config import JaznConfig
from latka_jazn.core import runtime_daemon as daemon
from latka_jazn.core.admission_owner_context import (
    ADMISSION_OWNER_HEADER, AUTHENTICATED_HTTP_OWNER, public_owner_digest,
)
from latka_jazn.mcp.server import JaznMcpServer


@contextmanager
def _running(root: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[daemon.JaznDaemonServer]:
    server = daemon.JaznDaemonServer(
        ("127.0.0.1", 0), daemon.JaznDaemonHandler,
        config=JaznConfig(root=root, memory_mode="off"),
        marker_path=root / "workspace_runtime" / "JAZN_ACTIVE_RUNTIME.json",
        hard_worker_process_isolation=False,
    )
    monkeypatch.setattr(server, "start_chat_worker", lambda: None)
    monkeypatch.setattr(server, "start_chat_watchdog", lambda: None)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        yield server
    finally:
        server.shutdown()
        worker.join(timeout=5.0)
        server.close_sessions()
        server.server_close()


def _gateway(server: daemon.JaznDaemonServer) -> SecureHostRuntimeGateway:
    return SecureHostRuntimeGateway(GatewayConfig(
        runtime_root=server.config.root, daemon_token=server.auth_token,
        daemon_url=f"http://127.0.0.1:{server.server_port}",
        timeout_seconds=5.0,
    ))


def _call(server: daemon.JaznDaemonServer, method: str, path: str,
          payload: dict[str, Any] | None = None, *, owner: str | None = None,
          authenticated: bool = True) -> tuple[int, dict[str, Any]]:
    headers = {"Content-Type": "application/json"}
    if authenticated:
        headers[daemon.DAEMON_AUTH_HEADER] = server.auth_token
    if owner is not None:
        headers[ADMISSION_OWNER_HEADER] = owner
    connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5.0)
    try:
        connection.request(method, path, body=None if payload is None else json.dumps(payload),
                           headers=headers)
        response = connection.getresponse()
        return response.status, json.loads(response.read())
    finally:
        connection.close()


def test_verified_mcp_context_reaches_daemon_and_does_not_bleed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stage05_public_context: Any,
) -> None:
    stage05_public_context(tmp_path, "alice", None)
    with _running(tmp_path, monkeypatch) as server:
        gateway = _gateway(server)
        mcp = object.__new__(JaznMcpServer)

        def dispatch(_name: str, _args: dict[str, Any], **_kwargs: Any) -> dict[str, Any]:
            return gateway._http_json("POST", "/chat-submit", {
                "message": "synthetic input", "request_id": "owned-r",
                "session_id": "synthetic-session", "client": "secure_mcp_gateway",
            }, retry_safe=False)

        monkeypatch.setattr(mcp, "call_tool", dispatch)
        result = mcp.call_public_authenticated("synthetic", {}, meta={"subject": "bob"},
                                               owner_subject="alice")
        assert result["accepted"] is True
        assert AUTHENTICATED_HTTP_OWNER.get() is None
        row = json.loads(server._chat_state_path.read_text(encoding="utf-8"))["jobs"][0]
        assert row["admission_owner_sha256"] == public_owner_digest("alice")
        assert "admission_owner_sha256" not in result
        assert server._chat_queue.qsize() == 1
        for subject in ("alice", "bob", None):
            token = AUTHENTICATED_HTTP_OWNER.set(subject)
            try:
                if subject == "alice":
                    assert gateway.result("owned-r")["request_id"] == "owned-r"
                    observed = daemon.chat_daemon_result(server.config, "owned-r", port=server.server_port)
                    assert observed["request_id"] == "owned-r" and observed["accepted"] is True
                else:
                    with pytest.raises(GatewayError, match="daemon_chat_owner_mismatch"):
                        gateway.result("owned-r")
            finally:
                AUTHENTICATED_HTTP_OWNER.reset(token)
        assert server._chat_queue.qsize() == 1


@pytest.mark.parametrize("kind", ["body", "malformed", "unauthenticated"])
def test_untrusted_or_invalid_owner_cannot_create_job(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str,
) -> None:
    with _running(tmp_path, monkeypatch) as server:
        payload = {"message": "synthetic", "request_id": "never-admitted"}
        owner = None
        if kind == "body":
            payload["admission_owner_sha256"] = public_owner_digest("alice")
        elif kind == "malformed":
            owner = "raw-subject"
        else:
            owner = public_owner_digest("alice")
        status, response = _call(server, "POST", "/chat-submit", payload,
                                 owner=owner, authenticated=kind != "unauthenticated")
        assert status in {400, 401, 403}
        assert response["ok"] is False
        assert server._chat_queue.empty()
        assert not server._chat_state_path.exists()


@pytest.mark.parametrize("owner", [None, public_owner_digest("bob")])
def test_ownerless_or_foreign_transport_cannot_poll_or_ack_owned_turn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, owner: str | None,
) -> None:
    with _running(tmp_path, monkeypatch) as server:
        payload = {"message": "synthetic canary", "request_id": "shared-r"}
        status, value = _call(server, "POST", "/chat-submit", payload,
                              owner=public_owner_digest("alice"))
        assert status == 202 and value["accepted"] is True
        before = server._chat_state_path.read_bytes()
        status, rejected = _call(server, "POST", "/chat-submit", payload, owner=owner)
        assert status == 409 and rejected["error_code"] == "request_id_conflict"
        status, rejected = _call(server, "GET", "/chat-result/shared-r", owner=owner)
        assert status == 403 and rejected["error_code"] == "daemon_chat_owner_mismatch"
        assert "synthetic canary" not in repr(rejected)
        status, rejected = _call(server, "POST", "/chat-finalization", {
            "request_id": "shared-r", "turn_id": "t", "trace_id": "tr",
            "request_contract_hash": "a" * 64, "outcome": "rejected",
            "reason": "synthetic", "terminal": True,
        }, owner=owner)
        assert status == 409 and rejected["error_code"] == "daemon_chat_owner_mismatch"
        assert server._chat_state_path.read_bytes() == before
        assert server._chat_queue.qsize() == 1


def test_owner_check_survives_daemon_restart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stage05_public_context: Any,
) -> None:
    stage05_public_context(tmp_path, "alice", None)
    alice = public_owner_digest("alice")
    with _running(tmp_path, monkeypatch) as first:
        status, value = _call(first, "POST", "/chat-submit", {
            "message": "synthetic", "request_id": "restart-r",
        }, owner=alice)
        assert status == 202 and value["accepted"] is True
    with _running(tmp_path, monkeypatch) as second:
        status, denied = _call(second, "GET", "/chat-result/restart-r",
                               owner=public_owner_digest("bob"))
        assert status == 403 and denied["error_code"] == "daemon_chat_owner_mismatch"
        status, recovered = _call(second, "GET", "/chat-result/restart-r", owner=alice)
        assert status == 200 and recovered["request_id"] == "restart-r"
        assert recovered["accepted"] is True
        assert second._chat_queue.empty()
