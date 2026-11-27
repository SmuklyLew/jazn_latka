"""F05/F01: opaque data remains exact; disconnect cannot alter admission."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from latka_jazn.config import JaznConfig
from latka_jazn.core import runtime_daemon as daemon


def _payload() -> dict[str, Any]:
    text = "braknie — endpointnie — procesdaemonu"
    return {
        "ok": True, "request_id": "braknie", "final_visible_text": text,
        "final_visible_integrity": {"text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()},
        "result": {"final_visible_text": text, "trace_id": "nieblokuje"},
    }


def _handler(state: daemon.DaemonRuntimeState) -> Any:
    return SimpleNamespace(
        path="/chat-result/braknie?secret=CANARY", command="GET",
        send_response=lambda *_a: None, send_header=lambda *_a: None,
        end_headers=lambda: None, close_connection=False,
        _daemon_server=lambda: SimpleNamespace(state=state),
    )


def test_exact_response_frame_and_atomic_file(tmp_path: Path) -> None:
    payload = _payload()
    path = tmp_path / "synthetic-ledger.json"
    daemon.write_json_atomic(path, payload)
    assert json.loads(path.read_text(encoding="utf-8")) == payload
    state = daemon.DaemonRuntimeState(root=str(tmp_path))
    handler = _handler(state)
    frames: list[bytes] = []
    headers: dict[str, str] = {}
    handler.send_header = lambda key, value: headers.update({key: value})
    handler.wfile = SimpleNamespace(write=frames.append, flush=lambda: None)
    daemon.JaznDaemonHandler._json_response(handler, payload)
    assert len(frames) == 1
    assert json.loads(frames[0].decode("utf-8")) == payload
    assert int(headers["Content-Length"]) == len(frames[0])
    assert state.response_write_error_count == 0


@pytest.mark.parametrize("stage", ["headers", "body", "flush"])
def test_delivery_failure_is_bounded_and_never_mutates_result(
    tmp_path: Path, stage: str,
) -> None:
    payload = _payload()
    before = json.dumps(payload, sort_keys=True)
    state = daemon.DaemonRuntimeState(root=str(tmp_path))
    handler = _handler(state)
    handler._record_response_write_failure = lambda *a, **k: daemon.JaznDaemonHandler._record_response_write_failure(handler, *a, **k)
    def disconnect(*_args: Any) -> None:
        raise BrokenPipeError("CANARY private exception")
    handler.wfile = SimpleNamespace(write=lambda _data: None, flush=lambda: None)
    if stage == "headers":
        handler.end_headers = disconnect
    elif stage == "body":
        handler.wfile.write = disconnect
    else:
        handler.wfile.flush = disconnect
    daemon.JaznDaemonHandler._json_response(handler, payload)
    assert handler.close_connection is True
    assert state.response_write_error_count == 1
    failure = state.last_response_write_failure
    assert failure is not None and failure["stage"] == stage
    assert failure["endpoint"] == "/chat-result"
    assert failure["request_id_sha256"] == hashlib.sha256(b"braknie").hexdigest()
    assert failure["delivery_confirmed"] is False
    assert "CANARY" not in repr(failure)
    assert json.dumps(payload, sort_keys=True) == before
    assert state.chat_job_submitted_count == state.chat_job_completed_count == 0


def test_opaque_request_id_survives_admission_and_restart(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for first in (True, False):
        server = daemon.JaznDaemonServer(
            ("127.0.0.1", 0), daemon.JaznDaemonHandler,
            config=JaznConfig(root=tmp_path, memory_mode="off"),
            marker_path=tmp_path / "workspace_runtime" / "JAZN_ACTIVE_RUNTIME.json",
            hard_worker_process_isolation=False,
        )
        monkeypatch.setattr(server, "start_chat_worker", lambda: None)
        monkeypatch.setattr(server, "start_chat_watchdog", lambda: None)
        try:
            job, created, error = server.submit_chat_job(
                request_id="braknie", user_text="synthetic", session_id="nieblokuje",
                input_field="message", no_carryover=False, client="synthetic",
            )
            assert job is not None and error is None and created is first
            assert job.request_id == "braknie" and job.session_id == "nieblokuje"
            assert server._chat_queue.qsize() == int(first)
            rows = json.loads(server._chat_state_path.read_text(encoding="utf-8"))["jobs"]
            assert rows[0]["request_id"] == "braknie"
        finally:
            server.close_sessions()
            server.server_close()
