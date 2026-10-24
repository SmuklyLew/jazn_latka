"""Real HTTP shutdown framing and fail-closed stop-client regressions."""
from __future__ import annotations

import json
import os
import threading
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

import pytest

from latka_jazn.config import JaznConfig
from latka_jazn.core import runtime_daemon


@pytest.mark.parametrize("request_body", [b"{}", b""])
def test_authenticated_shutdown_ack_with_real_http_request(
    tmp_path: Path, request_body: bytes
) -> None:
    """A Windows TCP peer must receive its short ACK without unread POST bytes."""
    fake = SimpleNamespace(
        daemon_instance_id="shutdown-http-regression",
        config=SimpleNamespace(root=tmp_path),
        state=SimpleNamespace(
            pid=os.getpid(),
            note_request=lambda: None,
            auth_failure_count=0,
            response_write_error_count=0,
            last_response_write_error=None,
        ),
        shutdown_requested=threading.Event(),
        auth_token="shutdown-test-token",
        shutdown=None,
    )

    class Handler(runtime_daemon.JaznDaemonHandler):
        def _daemon_server(self):  # type: ignore[override]
            return fake

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    fake.shutdown = server.shutdown
    serving = threading.Thread(target=server.serve_forever, daemon=True)
    serving.start()
    try:
        request = urllib.request.Request(
            f"http://127.0.0.1:{server.server_port}/shutdown",
            data=request_body,
            method="POST",
            headers={
                runtime_daemon.DAEMON_AUTH_HEADER: fake.auth_token,
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(request, timeout=3.0) as response:
            payload = json.loads(response.read().decode("utf-8"))
        assert payload["ok"] is True
        assert payload["shutdown_requested"] is True
        assert payload["daemon_instance_id"] == fake.daemon_instance_id
        assert payload["daemon_pid"] == os.getpid()
        assert fake.shutdown_requested.wait(timeout=2.0)
        serving.join(timeout=3.0)
        assert not serving.is_alive(), "HTTP server failed to stop"
        assert fake.state.response_write_error_count == 0
    finally:
        server.shutdown()
        serving.join(timeout=3.0)
        server.server_close()


def test_stop_client_uses_bodyless_post_after_identity_gate(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """No JSON body remains unread in the daemon's /shutdown handler."""
    before = {
        "endpoint_identity_matches": True,
        "resolved_active_root": str(tmp_path),
        "endpoint_reported_active_root": str(tmp_path),
        "daemon_pid": 424242,
    }
    after = {
        "active_state": "inactive",
        "endpoint_reachable": False,
        "pid_alive": False,
    }
    status_calls = 0

    def status(*_args: object, **_kwargs: object) -> dict[str, object]:
        nonlocal status_calls
        status_calls += 1
        return before if status_calls == 1 else after

    calls: list[tuple[str, object, str | None]] = []

    def http(
        method: str,
        _url: str,
        payload: object = None,
        *,
        timeout: float = 2.0,
        token: str | None = None,
    ) -> dict[str, object]:
        calls.append((method, payload, token))
        if method == "POST":
            return {"ok": True, "shutdown_requested": True}
        raise ConnectionRefusedError("stopped")

    monkeypatch.setattr(runtime_daemon, "status_daemon", status)
    monkeypatch.setattr(runtime_daemon, "http_json", http)
    monkeypatch.setattr(runtime_daemon, "read_daemon_auth_token", lambda _root: "verified-token")
    monkeypatch.setattr(runtime_daemon, "pid_is_alive", lambda _pid: False)

    result = runtime_daemon.stop_daemon(JaznConfig(root=tmp_path), timeout=1.0)
    assert result["ok"] is True
    assert result["stopped"] is True
    assert calls[0] == ("POST", None, "verified-token")
    assert status_calls == 2
