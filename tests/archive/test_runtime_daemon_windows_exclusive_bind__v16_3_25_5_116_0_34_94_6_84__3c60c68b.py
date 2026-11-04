"""A daemon listener must be the exclusive owner of its Windows TCP address."""
import os
import socket
import threading

import pytest

from latka_jazn.config import JaznConfig
from latka_jazn.core.runtime_daemon import JaznDaemonHandler, JaznDaemonServer, http_json

pytestmark = pytest.mark.skipif(os.name != "nt", reason="Native Windows Winsock ownership contract")


@pytest.fixture
def daemon(tmp_path):
    servers = []

    def create(address=("127.0.0.1", 0)):
        root = tmp_path / ("root-" + str(len(servers)))
        root.mkdir(exist_ok=True)
        server = JaznDaemonServer(address, JaznDaemonHandler,
                                  config=JaznConfig(root=root, memory_mode="off"),
                                  marker_path=root / "runtime/marker.json")
        servers.append(server)
        return server

    yield create
    for server in reversed(servers):
        server.close_sessions()
        server.server_close()


def test_daemon_sets_exclusive_ownership_before_bind(daemon):
    server = daemon()
    assert server.socket.getsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR) == 0
    assert server.socket.getsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE) != 0


def test_second_daemon_cannot_share_live_daemon_address(daemon):
    first = daemon()
    with pytest.raises(OSError):
        daemon(first.server_address)


def test_later_reusable_listener_cannot_claim_daemon_address(daemon):
    first = daemon()
    with socket.socket() as other:
        other.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        with pytest.raises(OSError):
            other.bind(first.server_address)


def test_daemon_refuses_an_existing_reusable_listener_before_writing_state(daemon, monkeypatch):
    from latka_jazn.core import runtime_daemon
    writes = []
    monkeypatch.setattr(runtime_daemon, "_write_private_token", lambda *args: writes.append(args))
    with socket.socket() as other:
        other.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        other.bind(("127.0.0.1", 0))
        other.listen()
        with pytest.raises(OSError):
            daemon(other.getsockname())
    assert writes == []


def test_cleanly_closed_unused_listener_can_be_reopened(daemon):
    first = daemon()
    address = first.server_address
    first.server_close()
    second = daemon(address)
    assert second.server_address == address


def test_missing_windows_exclusive_option_refuses_before_state_write(daemon, monkeypatch):
    from latka_jazn.core import runtime_daemon
    writes = []
    monkeypatch.delattr(socket, "SO_EXCLUSIVEADDRUSE")
    monkeypatch.setattr(runtime_daemon, "_write_private_token", lambda *args: writes.append(args))
    with pytest.raises(OSError, match="exclusive"):
        daemon()
    assert writes == []


def test_closed_http_listener_can_reopen_after_completed_request(daemon):
    first = daemon()
    address = first.server_address
    thread = threading.Thread(target=first.serve_forever, daemon=True)
    thread.start()
    try:
        observed = http_json("GET", f"http://127.0.0.1:{address[1]}/live")
        assert observed["daemon_instance_id"] == first.daemon_instance_id
    finally:
        first.shutdown()
        first.server_close()
        thread.join(5)
        assert not thread.is_alive()
    second = daemon(address)
    assert second.server_address == address
    assert second.daemon_instance_id != first.daemon_instance_id
