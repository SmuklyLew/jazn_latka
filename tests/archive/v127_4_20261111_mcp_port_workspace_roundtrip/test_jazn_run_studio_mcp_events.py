"""Regression: configured local MCP launch, truthful probes, durable GUI events."""
from __future__ import annotations

import json
from pathlib import Path
import queue
from typing import Any

import pytest

from tools.jazn_run_studio import core as studio_core, probes
from tools.jazn_run_studio.core import Controller, Settings, StudioError, load_settings, save_settings


@pytest.fixture
def root(tmp_path: Path) -> Path:
    (tmp_path / "latka_jazn").mkdir()
    (tmp_path / "latka_jazn" / "version.py").write_text("# test", encoding="utf-8")
    (tmp_path / "main.py").touch()
    (tmp_path / "run.py").touch()
    return tmp_path


class FakeSocket:
    def __init__(self, busy: bool = False):
        self.busy = busy
        self.address: tuple[str, int] | None = None

    def __enter__(self) -> FakeSocket:
        return self

    def __exit__(self, *_args: object) -> None:
        pass

    def settimeout(self, _timeout: float) -> None:
        pass

    def connect_ex(self, address: tuple[str, int]) -> int:
        self.address = address
        return 0 if self.busy else 111


@pytest.mark.parametrize("bad", [
    {"mcp_port": "22"},
    {"mcp_port": "65536"},
    {"mcp_port": "8080 --public-oauth"},
    {"mcp_port": "-1"},
    {"daemon_url": "http://localhost:8787"},
    {"daemon_url": "http://127.0.0.1:0"},
    {"daemon_url": "https://127.0.0.1:8787"},
    {"daemon_url": "http://127.0.0.1:8787/private"},
    {"daemon_url": "http://user:secret@127.0.0.1:8787"},
    {"daemon_url": "http://127.0.0.1:8787?secret=value"},
    {"daemon_url": "http://169.254.169.254:80"},
])
def test_invalid_gateway_and_daemon_configuration_rejected(bad: dict[str, str]) -> None:
    with pytest.raises(StudioError):
        Settings.validate(bad)


def test_configured_gateway_start_uses_explicit_local_mode(
    root: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings.validate({"mcp_port": "18086", "daemon_url": "http://127.0.0.1:8787"})
    controller = Controller(root, settings)
    socket = FakeSocket()
    monkeypatch.setattr(studio_core.socket, "socket", lambda: socket)
    launches: list[tuple[list[str], object]] = []
    monkeypatch.setattr(controller, "_launch", lambda job, argv, timeout: launches.append((argv, timeout)))
    # The gateway must pass its exact-interpreter import gate before spawning.
    # Keep this test focused on CLI argv while preflight failures are tested separately.
    monkeypatch.setattr(studio_core, "mcp_dependency_preflight", lambda *_args: {
        "mcp": True, "uvicorn": True, "starlette": True, "pydantic": True,
    })

    job = controller.start_service("gateway")
    assert job.key == "service:gateway"
    assert socket.address == ("127.0.0.1", 18086)
    assert len(launches) == 1
    argv, deadline = launches[0]
    assert argv[3].endswith("run.py")
    assert argv[4:] == [
        "mcp-http", "--loopback-dev", "--host", "127.0.0.1",
        "--port", "18086", "--daemon-url", "http://127.0.0.1:8787",
    ]
    assert "--public-oauth" not in argv
    assert deadline is None


def test_gateway_refuses_occupied_port_without_adopting_process(
    root: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller = Controller(root)
    monkeypatch.setattr(studio_core.socket, "socket", lambda: FakeSocket(busy=True))
    with pytest.raises(StudioError, match="zajęty"):
        controller.start_service("gateway")
    assert "service:gateway" not in controller.jobs


def test_gateway_probe_uses_selected_port_and_keeps_truth_boundary(
    root: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller = Controller(root, Settings(mcp_port="18086"))
    requested: list[str] = []
    def read_json(url: str, **_kwargs: Any) -> tuple[int, dict[str, Any]]:
        requested.append(url)
        return 200, {"ready": False, "gateway_live": True}
    monkeypatch.setattr(probes, "read_json", read_json)
    job = controller.probe("gateway")
    assert job.done.wait(5)
    assert requested == ["http://127.0.0.1:18086/readyz"]
    assert job.state == "failed" and job.error == "service_not_ready"
    assert any(kind == "probe" and payload.get("ready") is False
               for _key, kind, payload in list(controller.events.queue))


def test_read_json_refuses_non_probe_local_paths() -> None:
    for url in ("http://127.0.0.1:22/readyz",
                "http://127.0.0.1:18086/private",
                "http://127.0.0.1:18086/readyz?token=secret",
                "http://localhost:18086/readyz"):
        with pytest.raises(ValueError, match="Unsupported"):
            probes.read_json(url)


def test_selected_port_survives_settings_round_trip(root: Path) -> None:
    settings = Settings.validate({"mcp_port": "18086", "daemon_url": "http://127.0.0.1:8787"})
    saved = save_settings(root, settings, None)
    restored, digest = load_settings(root)
    assert digest == saved
    assert restored == settings
    stored = (root / "workspace_runtime" / "jazn_run_studio")
    assert stored.is_dir()
    assert "18086" in json.dumps(studio_core.asdict(restored))


def test_overflow_drops_logs_but_never_a_validated_final_or_state(root: Path) -> None:
    controller = Controller(root)
    for i in range(5000):
        controller.emit("diagnostics", "log", f"event-{i}")
    assert controller.events.full()
    final = {"text": "zaakceptowana wiadomość", "turn_id": "t", "trace_id": "x"}
    state = {"state": "succeeded", "error": None, "pid": 123}
    controller.emit("chat", "chat_final", final)
    controller.emit("probe:gateway", "state", state)
    controller.emit("status", "log", "extra log can be coalesced")
    assert controller.events.full()
    assert controller.critical_events.get_nowait() == ("chat", "chat_final", final)
    assert controller.critical_events.get_nowait() == ("probe:gateway", "state", state)
    with pytest.raises(queue.Empty):
        controller.critical_events.get_nowait()


def test_gui_drains_critical_events_even_with_full_log_queue(
    root: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    pytest.importorskip("PySide6")
    import os
    if os.name != "nt" and not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
        monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from tools.jazn_run_studio.window import Window
    app = QApplication.instance() or QApplication([])
    controller = Controller(root)
    window = Window(controller, smoke=True)
    for i in range(5000):
        controller.emit("diagnostics", "log", f"line-{i}")
    controller.emit("chat", "chat_final", {"text": "widoczny finał", "turn_id": "t", "trace_id": "x"})
    window.poll()
    assert "widoczny finał" in window.conversation.toPlainText()
    window.close()
