"""Regression: Windows daemon shutdown must not depend on HTTP ACK delivery."""
from __future__ import annotations

from http.client import HTTPMessage
from pathlib import Path
from types import SimpleNamespace
import threading

import pytest

from latka_jazn.core import runtime_daemon


@pytest.mark.parametrize("disconnect_during_ack", [False, True])
def test_authenticated_shutdown_is_scheduled_before_ack(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, disconnect_during_ack: bool
) -> None:
    shutdown_completed = threading.Event()
    replies: list[dict[str, object]] = []
    instance = SimpleNamespace(
        daemon_instance_id="test-runtime-instance",
        config=SimpleNamespace(root=tmp_path),
        state=SimpleNamespace(pid=12345, note_request=lambda: None),
        shutdown_requested=threading.Event(),
        shutdown=lambda: shutdown_completed.set(),
    )
    handler = object.__new__(runtime_daemon.JaznDaemonHandler)
    # The real BaseHTTPRequestHandler builds headers when parsing the request.
    # Set a valid, bodyless HTTP message for this deliberately uninitialized
    # unit-test instance. Full socket/body framing is tested separately.
    handler.headers = HTTPMessage()
    monkeypatch.setattr(
        runtime_daemon.JaznDaemonHandler, "_loopback_only", lambda _self: True
    )
    monkeypatch.setattr(
        runtime_daemon.JaznDaemonHandler,
        "_request_path_and_query", lambda _self: ("/shutdown", {}),
    )
    monkeypatch.setattr(
        runtime_daemon.JaznDaemonHandler, "_authenticated",
        lambda _self, *, mutating=False: mutating,
    )
    monkeypatch.setattr(
        runtime_daemon.JaznDaemonHandler, "_daemon_server",
        lambda _self: instance,
    )

    def reply(_self: object, payload: dict[str, object]) -> None:
        assert instance.shutdown_requested.is_set()
        replies.append(payload)
        if disconnect_during_ack:
            raise ConnectionAbortedError("simulated client disconnect")

    monkeypatch.setattr(runtime_daemon.JaznDaemonHandler, "_json_response", reply)
    if disconnect_during_ack:
        with pytest.raises(ConnectionAbortedError, match="simulated"):
            handler.do_POST()
    else:
        handler.do_POST()

    assert shutdown_completed.wait(timeout=2.0)
    assert len(replies) == 1
    assert replies[0]["ok"] is True
    assert replies[0]["shutdown_requested"] is True
    assert replies[0]["daemon_instance_id"] == "test-runtime-instance"
    assert replies[0]["daemon_pid"] == 12345
    assert replies[0]["active_root"] == str(tmp_path)
    assert len(str(replies[0])) < 1024


def test_unauthenticated_shutdown_never_starts_teardown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    instance = SimpleNamespace(shutdown_requested=threading.Event())
    handler = object.__new__(runtime_daemon.JaznDaemonHandler)
    monkeypatch.setattr(runtime_daemon.JaznDaemonHandler, "_loopback_only", lambda _: True)
    monkeypatch.setattr(
        runtime_daemon.JaznDaemonHandler,
        "_request_path_and_query", lambda _: ("/shutdown", {}),
    )
    monkeypatch.setattr(
        runtime_daemon.JaznDaemonHandler, "_authenticated",
        lambda _, *, mutating=False: False,
    )
    monkeypatch.setattr(runtime_daemon.JaznDaemonHandler, "_daemon_server", lambda _: instance)
    handler.do_POST()
    assert not instance.shutdown_requested.is_set()


def test_shutdown_marker_reuses_last_evidence_without_full_reverification(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Only startup verifies the package; the final marker must be bounded."""
    from latka_jazn.config import JaznConfig

    class FakeServer:
        def __init__(self) -> None:
            self.state = SimpleNamespace(pid=12345, status="running")
            self.daemon_instance_id = "verified-instance"
            self.shutdown_requested = threading.Event()
            self.rest_cycle_controller = None
            self.memory_sync_controller = None
            self.auth_token_path = tmp_path / "nonexistent-token"

        def refresh_timestamp_contract(self, **_kwargs: object) -> None:
            return None

        def write_marker(self) -> None:
            return None

        def start_heartbeat(self) -> None:
            return None

        def serve_forever(self, **_kwargs: object) -> None:
            return None

        def close_sessions(self) -> None:
            return None

        def server_close(self) -> None:
            return None

        def marker_payload(self, **_kwargs: object) -> None:
            raise AssertionError("expensive active marker must not rebuild on stop")

    saved: list[dict[str, object]] = []
    server = FakeServer()
    verified = {"count": 0}

    def verify_once(_root: Path) -> dict[str, object]:
        verified["count"] += 1
        return {"ok": True}

    monkeypatch.setattr(runtime_daemon, "verify_package_integrity_manifest", verify_once)
    monkeypatch.setattr(
        runtime_daemon, "read_source_provenance",
        lambda *_a, **_k: SimpleNamespace(
            to_dict=lambda: {"status": "verified_export_without_git_history"}
        ),
    )
    monkeypatch.setattr(runtime_daemon, "build_runtime_write_access_status", lambda *_a, **_k: None)
    monkeypatch.setattr(runtime_daemon, "write_active_runtime_marker", lambda *_a, **_k: None)
    monkeypatch.setattr(runtime_daemon, "JaznDaemonServer", lambda *_a, **_k: server)
    monkeypatch.setattr(runtime_daemon, "_emit_visible_daemon_event", lambda *_a, **_k: None)
    monkeypatch.setattr(
        runtime_daemon, "read_json_file",
        lambda _path: {
            "active_root": str(tmp_path),
            "runtime_daemon": {"status": "active", "unrelated": "preserved"},
            "sentinel": "retain",
        },
    )
    monkeypatch.setattr(
        runtime_daemon, "write_json_atomic",
        lambda _path, payload: saved.append(dict(payload)),
    )
    monkeypatch.setattr(runtime_daemon, "_cleanup_owned_pid_file", lambda *_a, **_k: None)

    result = runtime_daemon.run_daemon(JaznConfig(root=tmp_path), port=0)
    assert result == 0
    assert verified["count"] == 1
    assert server.shutdown_requested.is_set()
    assert server.state.status == runtime_daemon.DAEMON_MARKER_STATUS_STOPPED
    assert len(saved) == 1
    marker = saved[0]
    assert marker["sentinel"] == "retain"
    assert marker["runtime_process_active"] is False
    assert marker["active_state"] == "inactive"
    assert marker["daemon_instance_id"] == "verified-instance"
    nested = marker["runtime_daemon"]
    assert isinstance(nested, dict)
    assert nested["status"] == runtime_daemon.DAEMON_MARKER_STATUS_STOPPED
