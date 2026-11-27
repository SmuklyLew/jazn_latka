"""F01: storage barriers and explicit uncertainty over authenticated HTTP."""
from __future__ import annotations

import json
import os
from pathlib import Path
import threading
import urllib.error
import urllib.request
from typing import Any

import pytest

from latka_jazn.config import JaznConfig
from latka_jazn.core import runtime_daemon as daemon


def _server(root: Path, monkeypatch: pytest.MonkeyPatch) -> daemon.JaznDaemonServer:
    server = daemon.JaznDaemonServer(
        ("127.0.0.1", 0), daemon.JaznDaemonHandler,
        config=JaznConfig(root=root, memory_mode="off"),
        marker_path=root / "workspace_runtime" / "JAZN_ACTIVE_RUNTIME.json",
        hard_worker_process_isolation=False,
    )
    monkeypatch.setattr(server, "start_chat_worker", lambda: None)
    monkeypatch.setattr(server, "start_chat_watchdog", lambda: None)
    return server


def _submit(server: daemon.JaznDaemonServer):
    return server.submit_chat_job(
        request_id="synthetic-f01", user_text="synthetic input",
        session_id="synthetic-session", input_field="message",
        no_carryover=False, client="synthetic-client",
    )


def test_durable_atomic_write_flushes_before_publish_and_syncs_parent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "ledger.json"
    events: list[str] = []
    real_fsync, real_replace = os.fsync, os.replace
    def sync(fd: int) -> None:
        events.append("sync")
        real_fsync(fd)
    def replace(src: Any, dst: Any) -> None:
        assert json.loads(Path(src).read_text(encoding="utf-8")) == {"ok": True}
        events.append("replace")
        real_replace(src, dst)
    monkeypatch.setattr(os, "fsync", sync)
    monkeypatch.setattr(os, "replace", replace)
    daemon.write_json_atomic(target, {"ok": True}, durable=True)
    assert events == (["sync", "replace", "sync"] if os.name == "posix" else ["sync", "replace"])
    assert json.loads(target.read_text(encoding="utf-8")) == {"ok": True}


def test_file_sync_failure_does_not_publish(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "ledger.json"
    target.write_text('{"previous":true}', encoding="utf-8")
    def fail(_fd: int) -> None:
        raise OSError("synthetic sync failure")
    monkeypatch.setattr(os, "fsync", fail)
    with pytest.raises(OSError, match="synthetic sync failure"):
        daemon.write_json_atomic(target, {"new": True}, durable=True)
    assert json.loads(target.read_text(encoding="utf-8")) == {"previous": True}
    assert not list(tmp_path.glob(".*.tmp"))


def test_ambiguous_publish_never_enqueues_or_acknowledges(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = _server(tmp_path, monkeypatch)
    original_sync = daemon._sync_json_parent_directory
    try:
        def fail_ledger(path: Path) -> None:
            if path == first._chat_state_path:
                raise OSError("synthetic directory sync failure after replace")
            original_sync(path)
        monkeypatch.setattr(daemon, "_sync_json_parent_directory", fail_ledger)
        job, created, error = _submit(first)
        assert job is None and not created and error is not None
        assert error["error_code"] == "daemon_chat_state_persist_failed"
        assert error["must_not_resubmit_user_message"] is True
        assert first._chat_queue.empty()
        assert first.chat_job_summary()["submitted_total"] == 0
        assert json.loads(first._chat_state_path.read_text(encoding="utf-8"))["jobs"][0]["request_id"] == "synthetic-f01"
        again, created, error = _submit(first)
        assert again is None and not created and error is not None
        assert error["error_code"] == "daemon_chat_ledger_unresolved_record"
    finally:
        monkeypatch.setattr(daemon, "_sync_json_parent_directory", original_sync)
        first.close_sessions()
        first.server_close()
    second = _server(tmp_path, monkeypatch)
    try:
        recovered, created, error = _submit(second)
        assert recovered is not None and not created and error is None
        assert recovered.terminal()
        assert second._chat_queue.empty()
        assert second.chat_job_summary()["submitted_total"] == 0
    finally:
        second.close_sessions()
        second.server_close()


@pytest.mark.parametrize(("damage", "expected_status", "expected_code"), [
    ("virgin", 404, "chat_job_not_found"),
    ("missing", 503, "daemon_chat_ledger_missing"),
    ("corrupt", 503, "daemon_chat_ledger_invalid"),
    ("unreadable", 503, "daemon_chat_ledger_unreadable"),
    ("unresolved", 503, "daemon_chat_ledger_unresolved_record"),
])
def test_authenticated_http_poll_distinguishes_absence_from_unverified_history(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    damage: str, expected_status: int, expected_code: str,
) -> None:
    server = _server(tmp_path, monkeypatch)
    path = server._chat_state_path
    path.parent.mkdir(parents=True, exist_ok=True)
    if damage == "missing":
        server._chat_ledger_guard_path.write_text("{}", encoding="utf-8")
    elif damage == "corrupt":
        path.write_text("{broken", encoding="utf-8")
    elif damage == "unresolved":
        path.write_text(json.dumps({"jobs": [{"request_id": "synthetic-f01",
            "status": "completed", "request_fingerprint": None}]}), encoding="utf-8")
    elif damage == "unreadable":
        original = Path.read_text
        def deny(candidate: Path, *args: Any, **kwargs: Any) -> str:
            if candidate == path:
                raise PermissionError("synthetic private error")
            return original(candidate, *args, **kwargs)
        monkeypatch.setattr(Path, "read_text", deny)
    serving = threading.Thread(target=server.serve_forever, daemon=True)
    serving.start()
    try:
        request = urllib.request.Request(
            f"http://127.0.0.1:{server.server_port}/chat-result/synthetic-f01",
            headers={daemon.DAEMON_AUTH_HEADER: server.auth_token},
        )
        with pytest.raises(urllib.error.HTTPError) as failure:
            urllib.request.urlopen(request, timeout=5.0)
        with failure.value as response:
            payload = json.loads(response.read().decode("utf-8"))
            assert response.code == expected_status
        assert payload["error_code"] == expected_code
        assert payload["request_id"] == "synthetic-f01"
        assert payload["ok"] is False
        if expected_status == 503:
            assert payload["must_not_resubmit_user_message"] is True
            assert payload["admission_history_verified"] is False
            assert payload["daemon_instance_id"] == server.daemon_instance_id
            assert "synthetic private error" not in repr(payload)
            assert "result" not in payload
        assert server._chat_queue.empty()
        assert server.chat_job_summary()["submitted_total"] == 0
    finally:
        server.shutdown()
        serving.join(timeout=5.0)
        server.close_sessions()
        server.server_close()
