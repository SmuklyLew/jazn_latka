from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import json
import os
import socket
import threading
import time
import urllib.error
import urllib.request

import pytest

from latka_jazn.config import JaznConfig
from latka_jazn.core import runtime_daemon
from latka_jazn.core.turn_timeout import RuntimeSessionWorker, RuntimeTurnTimeoutError


class _Session:
    created = 0
    closed = 0

    def __init__(self, _config, **kwargs) -> None:
        type(self).created += 1
        self.state = SimpleNamespace(session_id=kwargs.get("session_id"))

    def process_user_text(self, user_text: str, **_kwargs) -> dict:
        return {"ok": True, "final_visible_text": user_text}

    def close(self) -> None:
        type(self).closed += 1


class _SlowStartupSession(_Session):
    started = threading.Event()
    release = threading.Event()

    def __init__(self, _config, **kwargs) -> None:
        type(self).started.set()
        type(self).release.wait(2.0)
        super().__init__(_config, **kwargs)


def _server(tmp_path: Path) -> runtime_daemon.JaznDaemonServer:
    root = tmp_path.resolve()
    marker = root / "workspace_runtime" / "JAZN_ACTIVE_RUNTIME.json"
    return runtime_daemon.JaznDaemonServer(
        ("127.0.0.1", 0),
        runtime_daemon.JaznDaemonHandler,
        config=JaznConfig(root=root),
        marker_path=marker,
        session_factory=_Session,
        execution_timeout_seconds=0.25,
    )


def _start(server: runtime_daemon.JaznDaemonServer) -> threading.Thread:
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return thread


def _request(server: runtime_daemon.JaznDaemonServer, path: str, *, token: str | None, origin: str | None = None):
    data = json.dumps({"message": "hej", "request_id": "security-test"}).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token:
        headers[runtime_daemon.DAEMON_AUTH_HEADER] = token
    if origin:
        headers["Origin"] = origin
    request = urllib.request.Request(
        runtime_daemon.daemon_url("127.0.0.1", int(server.server_address[1]), path),
        data=data,
        method="POST",
        headers=headers,
    )
    return urllib.request.urlopen(request, timeout=2.0)


def test_chat_requires_capability_token(tmp_path: Path) -> None:
    server = _server(tmp_path)
    thread = _start(server)
    try:
        with pytest.raises(urllib.error.HTTPError) as caught:
            _request(server, "/chat-submit", token=None)
        assert caught.value.code == 401
        body = json.loads(caught.value.read().decode("utf-8"))
        assert body["error_code"] == "daemon_auth_required"

        with _request(server, "/chat-submit", token=server.auth_token) as response:
            body = json.loads(response.read().decode("utf-8"))
        assert body["accepted"] is True
    finally:
        server.shutdown()
        server.close_sessions()
        server.server_close()
        thread.join(timeout=2.0)


def test_chat_rejects_wrong_non_empty_capability_token_without_mutation(tmp_path: Path) -> None:
    _Session.created = 0
    _Session.closed = 0
    server = _server(tmp_path)
    thread = _start(server)
    try:
        with pytest.raises(urllib.error.HTTPError) as caught:
            _request(server, "/chat-submit", token="definitely-wrong-capability-token")

        assert caught.value.code == 401
        body = json.loads(caught.value.read().decode("utf-8"))
        assert body["error_code"] == "daemon_auth_required"
        assert server.state.auth_failure_count == 1
        assert server.chat_job_summary()["submitted_total"] == 0
        assert _Session.created == 0
    finally:
        server.shutdown()
        server.close_sessions()
        server.server_close()
        thread.join(timeout=2.0)


def test_repeated_unauthenticated_posts_return_http_401_without_connection_reset(
    tmp_path: Path,
) -> None:
    server = _server(tmp_path)
    thread = _start(server)
    try:
        for _attempt in range(12):
            with pytest.raises(urllib.error.HTTPError) as caught:
                _request(server, "/chat-submit", token=None)
            assert caught.value.code == 401
            body = json.loads(caught.value.read().decode("utf-8"))
            assert body["error_code"] == "daemon_auth_required"
    finally:
        server.shutdown()
        server.close_sessions()
        server.server_close()
        thread.join(timeout=2.0)


def test_mutating_browser_origin_is_rejected(tmp_path: Path) -> None:
    server = _server(tmp_path)
    thread = _start(server)
    try:
        with pytest.raises(urllib.error.HTTPError) as caught:
            _request(server, "/chat-submit", token=server.auth_token, origin="https://example.invalid")
        assert caught.value.code == 403
        body = json.loads(caught.value.read().decode("utf-8"))
        assert body["error_code"] == "browser_origin_not_allowed"
    finally:
        server.shutdown()
        server.close_sessions()
        server.server_close()
        thread.join(timeout=2.0)


def test_invalid_content_length_returns_bad_request_without_hanging(tmp_path: Path) -> None:
    server = _server(tmp_path)
    thread = _start(server)
    port = int(server.server_address[1])
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=2.0) as sock:
            request = (
                "POST /chat-submit HTTP/1.1\r\n"
                f"Host: 127.0.0.1:{port}\r\n"
                f"{runtime_daemon.DAEMON_AUTH_HEADER}: {server.auth_token}\r\n"
                "Content-Type: application/json\r\n"
                "Content-Length: nope\r\n"
                "Connection: close\r\n\r\n"
            ).encode("ascii")
            sock.sendall(request)
            raw = b""
            while True:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                raw += chunk
        assert b"400 Bad Request" in raw
        assert b"invalid_content_length" in raw
    finally:
        server.shutdown()
        server.close_sessions()
        server.server_close()
        thread.join(timeout=2.0)


def test_marker_failure_does_not_destroy_completed_job(tmp_path: Path) -> None:
    server = _server(tmp_path)
    server.write_marker = lambda **_kwargs: (_ for _ in ()).throw(OSError("marker unavailable"))  # type: ignore[method-assign]
    try:
        job, created, error = server.submit_chat_job(
            user_text="gotowy final",
            input_field="test",
            session_id="marker-session",
            no_carryover=False,
            client="test",
            request_id="marker-failure",
        )
        assert created is True and error is None and job is not None
        assert job.done_event.wait(2.0)
        assert job.status == "completed"
        assert job.result is not None and job.result["ok"] is True
        assert job.result["daemon"]["marker_write_degraded"] is True
        assert server.state.marker_write_failure_count >= 1
    finally:
        server.close_sessions()
        server.server_close()


def test_recovery_persist_failure_does_not_kill_worker(tmp_path: Path) -> None:
    server = _server(tmp_path)
    server.write_marker = lambda **_kwargs: {"manifest_current_sha256": None}  # type: ignore[method-assign]
    server._persist_chat_jobs_locked_unsafe = lambda: (_ for _ in ()).throw(OSError("recovery unavailable"))  # type: ignore[method-assign]
    try:
        job, created, error = server.submit_chat_job(
            user_text="hej",
            input_field="test",
            session_id="recovery-session",
            no_carryover=False,
            client="test",
            request_id="recovery-failure",
        )
        assert created is True and error is None and job is not None
        assert job.done_event.wait(2.0)
        assert job.status == "completed"
        summary = server.chat_job_summary()
        assert summary["worker_alive"] is True
        assert server.state.recovery_persist_failure_count >= 1
    finally:
        server.close_sessions()
        server.server_close()


def test_session_limit_is_fail_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JAZN_DAEMON_MAX_SESSIONS", "1")
    server = _server(tmp_path)
    try:
        first, _ = server.get_session("first")
        assert first.usable is True
        with pytest.raises(RuntimeError, match="daemon_session_limit_reached"):
            server.get_session("second")
        assert server.state.session_limit_rejection_count == 1
    finally:
        server.close_sessions()
        server.server_close()


def test_corrupt_recovery_state_is_quarantined(tmp_path: Path) -> None:
    root = tmp_path.resolve()
    state_path = root / "workspace_runtime" / "daemon_chat_jobs.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text("{broken", encoding="utf-8")
    server = _server(tmp_path)
    try:
        assert not state_path.exists()
        quarantined = list(state_path.parent.glob("daemon_chat_jobs.json.corrupt-*"))
        assert len(quarantined) == 1
        assert server.state.last_recovery_persist_error
    finally:
        server.close_sessions()
        server.server_close()


def test_startup_timeout_closes_late_session(tmp_path: Path) -> None:
    _SlowStartupSession.created = 0
    _SlowStartupSession.closed = 0
    _SlowStartupSession.started = threading.Event()
    _SlowStartupSession.release = threading.Event()
    config = SimpleNamespace(runtime_turn_timeout_seconds=0.01, audit_db_path=None)
    with pytest.raises(RuntimeTurnTimeoutError):
        RuntimeSessionWorker(
            session_factory=_SlowStartupSession,
            config=config,
            session_id="late",
            no_carryover=False,
            source_client="test",
            command="startup-test",
            timeout_seconds=0.01,
        )
    assert _SlowStartupSession.started.wait(1.0)
    _SlowStartupSession.release.set()
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline and _SlowStartupSession.closed == 0:
        time.sleep(0.01)
    assert _SlowStartupSession.created == 1
    assert _SlowStartupSession.closed == 1
