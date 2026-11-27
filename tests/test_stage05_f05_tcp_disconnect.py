"""F05/F01: a lost TCP response is not a new admission or execution.

Only the timing of the actual socket reset is controlled. No write exception
is fabricated, no real model is invoked and no finalization is asserted for
the synthetic terminal fixture.
"""
from __future__ import annotations

import hashlib
import http.client
import json
import os
from pathlib import Path
import select
import socket
import struct
import threading
from typing import Any

import pytest

from latka_jazn.config import JaznConfig
from latka_jazn.core import runtime_daemon as daemon


@pytest.mark.parametrize("stage", ["headers", "body"])
def test_real_tcp_reset_preserves_admission_and_exact_poll(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stage: str,
) -> None:
    request_id = "synthetic-f05-braknie"
    user_text = "syntetyczne — braknie"
    answer = "syntetyczny wynik — endpointnie — procesdaemonu"
    poll_path = f"/chat-result/{request_id}"
    target_path = "/chat-submit" if stage == "headers" else poll_path
    ready = threading.Event()
    release = threading.Event()
    finished = threading.Event()
    errors: list[str] = []

    class ResetGateHandler(daemon.JaznDaemonHandler):
        def _json_response(self, payload: dict[str, Any], *, status: int = 200) -> None:
            targeted = self.path == target_path and not ready.is_set()
            try:
                super()._json_response(payload, status=status)
            finally:
                if targeted:
                    finished.set()

        def end_headers(self) -> None:
            if self.path != target_path or ready.is_set():
                super().end_headers()
                return
            if stage == "body":
                super().end_headers()
            ready.set()
            if not release.wait(10.0):
                errors.append("client reset gate timed out")
                return
            # A readable/exceptional socket with no new client data means the
            # close has reached the server; do not consume its pending error.
            readable, _, exceptional = select.select(
                [self.connection], [], [self.connection], 5.0,
            )
            if not readable and not exceptional:
                errors.append("peer reset not observed")
                return
            if stage == "headers":
                super().end_headers()

    server = daemon.JaznDaemonServer(
        ("127.0.0.1", 0), ResetGateHandler,
        config=JaznConfig(root=tmp_path, memory_mode="off"),
        marker_path=tmp_path / "workspace_runtime" / "JAZN_ACTIVE_RUNTIME.json",
        hard_worker_process_isolation=False,
    )
    monkeypatch.setattr(server, "start_chat_worker", lambda: None)
    monkeypatch.setattr(server, "start_chat_watchdog", lambda: None)
    payload = {
        "request_id": request_id, "message": user_text,
        "session_id": "synthetic-f05-session", "client": "synthetic",
        "expected_daemon_instance_id": server.daemon_instance_id,
    }
    synthetic_result = {
        "ok": True, "final_visible_text": answer,
        "final_visible_integrity": {"text_sha256": hashlib.sha256(answer.encode("utf-8")).hexdigest()},
    }
    if stage == "body":
        # Prepare a deterministic terminal job using the real admission and
        # persistence path, but no model or claimed accepted finalization.
        job, created, error = server.submit_chat_job(
            request_id=request_id, user_text=user_text, input_field="message",
            session_id="synthetic-f05-session", client="synthetic", no_carryover=False,
        )
        assert job is not None and created and error is None
        assert server._chat_queue.get_nowait() is job
        server._chat_queue.task_done()
        with server._chat_jobs_lock:
            job.status = "completed"
            job.result = synthetic_result
            job.completed_at_utc = daemon.utc_now_iso()
            server.state.chat_job_completed_count += 1
            job.done_event.set()
            assert server._persist_chat_jobs_locked(stage="synthetic_f05_terminal")

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        method = "POST" if stage == "headers" else "GET"
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8") if method == "POST" else b""
        headers = (
            f"{method} {target_path} HTTP/1.1\r\n"
            f"Host: 127.0.0.1:{server.server_port}\r\n"
            f"{daemon.DAEMON_AUTH_HEADER}: {server.auth_token}\r\n"
            "Content-Type: application/json\r\n"
            f"Content-Length: {len(body)}\r\n"
            "Connection: close\r\n\r\n"
        ).encode("ascii")
        with socket.create_connection(("127.0.0.1", server.server_port), timeout=5.0) as client:
            client.sendall(headers + body)
            assert ready.wait(10.0), "server did not reach actual HTTP response"
            before = server._chat_state_path.read_bytes()
            assert server.chat_job_summary()["submitted_total"] == 1
            # Winsock uses two unsigned shorts; Linux uses two ints.
            linger = struct.pack("HH" if os.name == "nt" else "ii", 1, 0)
            client.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, linger)
        release.set()
        assert finished.wait(10.0), "HTTP handler did not finish"
        assert not errors
        assert server.state.response_write_error_count == 1
        failure = server.state.last_response_write_failure
        assert failure is not None
        assert failure["stage"] == stage
        assert failure["endpoint"] == ("/chat-submit" if stage == "headers" else "/chat-result")
        assert failure["request_id_sha256"] == hashlib.sha256(request_id.encode("utf-8")).hexdigest()
        assert failure["delivery_confirmed"] is False
        assert user_text not in repr(failure)
        assert answer not in repr(failure)
        assert server._chat_state_path.read_bytes() == before

        # No POST retry: use the same request ID on a fresh TCP connection.
        connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5.0)
        try:
            connection.request("GET", poll_path, headers={daemon.DAEMON_AUTH_HEADER: server.auth_token})
            response = connection.getresponse()
            assert response.status == (202 if stage == "headers" else 200)
            result = json.loads(response.read().decode("utf-8"))
        finally:
            connection.close()
        assert result["request_id"] == request_id
        assert result["daemon_instance_id"] == server.daemon_instance_id
        assert result["accepted"] is True
        assert result["created"] is False
        assert result["user_text_sha256"] == hashlib.sha256(user_text.encode("utf-8")).hexdigest()
        assert result["job_status"] == ("queued" if stage == "headers" else "completed")
        if stage == "body":
            assert result["result"] == synthetic_result
        assert server.chat_job_summary()["submitted_total"] == 1
        assert server.state.chat_job_completed_count == int(stage == "body")
        assert server._chat_queue.qsize() == int(stage == "headers")
        assert server.state.response_write_error_count == 1
        assert server._chat_state_path.read_bytes() == before
    finally:
        release.set()
        server.shutdown()
        thread.join(timeout=5.0)
        server.close_sessions()
        server.server_close()
