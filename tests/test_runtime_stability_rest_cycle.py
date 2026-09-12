from __future__ import annotations

from pathlib import Path

import pytest

from latka_jazn.config import JaznConfig
from latka_jazn.core import runtime_daemon


def _server(tmp_path: Path) -> runtime_daemon.JaznDaemonServer:
    config = JaznConfig(root=tmp_path, rest_cycle_enabled=True, rest_poll_seconds=0.1)
    marker = tmp_path / "workspace_runtime" / "JAZN_ACTIVE_RUNTIME.json"
    marker.parent.mkdir(parents=True, exist_ok=True)
    return runtime_daemon.JaznDaemonServer(
        ("127.0.0.1", 0), runtime_daemon.JaznDaemonHandler,
        config=config, marker_path=marker, heartbeat_interval=60.0,
    )


def test_daemon_owns_rest_controller_without_new_port(tmp_path: Path) -> None:
    server = _server(tmp_path)
    try:
        assert server.rest_cycle_controller is not None
        status = server.rest_cycle_status()
        assert status["enabled"] is True
        assert status["automatic_l3_allowed"] is False
        assert status["external_tool_authority"] is False
        assert server.server_address[0] == "127.0.0.1"
    finally:
        server.close_sessions()
        server.server_close()


def test_rest_initialization_failure_is_fail_soft_for_dialogue(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    class BrokenRest:
        def __init__(self, *_args, **_kwargs) -> None:
            raise RuntimeError("synthetic rest failure")

    monkeypatch.setattr(runtime_daemon, "RestCycleController", BrokenRest)
    server = _server(tmp_path)
    try:
        status = server.rest_cycle_status()
        assert status["state"] == "unavailable"
        assert status["ordinary_dialogue_allowed"] is True
        assert "synthetic rest failure" in str(status["init_error"])
    finally:
        server.close_sessions()
        server.server_close()
