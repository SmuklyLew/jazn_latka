"""Regression: Windows daemon shutdown must not depend on HTTP ACK delivery."""
from __future__ import annotations

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
