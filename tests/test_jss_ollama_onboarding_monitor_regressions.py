"""Isolated contracts for official Ollama onboarding, CLI ownership and passive monitor.

No real Ollama process, daemon, MEMORY or network access is used here.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools.jazn_run_studio import probes
from tools.jazn_run_studio.core import Controller, Settings


def test_tags_and_loaded_models_are_separate_api_observations(monkeypatch) -> None:
    urls = []

    def fake_read(url: str):
        urls.append(url)
        if url.endswith("/api/tags"):
            return 200, {"models": [{"name": "gemma3:latest"}, {"name": "other"}]}
        assert url.endswith("/api/ps")
        return 200, {"models": [{"name": "gemma3:latest"}]}

    monkeypatch.setattr(probes, "read_json", fake_read)
    result = probes.ollama("gemma3:latest")
    assert urls == ["http://127.0.0.1:11434/api/tags",
                    "http://127.0.0.1:11434/api/ps"]
    assert result["models"] == ["gemma3:latest", "other"]
    assert result["loaded_models"] == ["gemma3:latest"]
    assert result["loaded_models_state"] == "verified"
    assert result["selected_model_present"] is True
    assert result["generation_verified"] is False
    assert result["accepted_visible_turn"] is False


def test_loaded_models_fail_closed_without_erasing_valid_inventory(monkeypatch) -> None:
    def unavailable(url: str):
        if url.endswith("/api/tags"):
            return 200, {"models": [{"name": "gemma3:latest"}]}
        raise ConnectionRefusedError("synthetic /api/ps outage")

    monkeypatch.setattr(probes, "read_json", unavailable)
    result = probes.ollama("gemma3:latest")
    assert result["endpoint_reachable"] is True
    assert result["selected_model_present"] is True
    assert result["loaded_models_state"] == "unavailable"
    assert result["loaded_models"] == []
    assert result["generation_verified"] is False

    def invalid(url: str):
        if url.endswith("/api/tags"):
            return 200, {"models": [{"name": "gemma3:latest"}]}
        return 200, {"models": [{"name": 42}]}

    monkeypatch.setattr(probes, "read_json", invalid)
    assert probes.ollama("gemma3:latest")["loaded_models_state"] == "invalid_response"


def test_api_ps_is_permitted_only_on_local_loopback(monkeypatch) -> None:
    class Response:
        code = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self, _size):
            return json.dumps({"models": []}).encode("utf-8")

    opened = []
    monkeypatch.setattr(
        probes, "build_opener",
        lambda *_handlers: SimpleNamespace(
            open=lambda request, **_kw: opened.append(request.full_url) or Response()
        ),
    )
    status, payload = probes.read_json("http://127.0.0.1:11434/api/ps")
    assert status == 200 and payload == {"models": []}
    assert opened == ["http://127.0.0.1:11434/api/ps"]
    for url in ("http://example.com:11434/api/ps",
                "http://127.0.0.1:11434/api/delete",
                "http://127.0.0.1:11434/api/ps?token=x"):
        with pytest.raises(ValueError):
            probes.read_json(url)
    assert len(opened) == 1


@pytest.fixture
def core(tmp_path: Path):
    (tmp_path / "latka_jazn").mkdir()
    for marker in ("latka_jazn/version.py", "run.py", "main.py"):
        (tmp_path / marker).touch()
    return Controller(tmp_path, Settings(model="gemma3:latest", theme="dark"))


def test_occupied_ollama_port_connects_without_spawning_second_server(core, monkeypatch) -> None:
    from tools.jazn_run_studio import core as module

    class OccupiedSocket:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def settimeout(self, _timeout):
            pass

        def connect_ex(self, address):
            assert address == ("127.0.0.1", 11434)
            return 0

    monkeypatch.setattr(module.socket, "socket", lambda: OccupiedSocket())
    monkeypatch.setattr(core, "probe",
                        lambda key: SimpleNamespace(key="probe:" + key))
    monkeypatch.setattr(core, "start_service",
                        lambda *_args: pytest.fail("must not spawn Ollama"))
    assert core.ensure_ollama().key == "probe:ollama"


def test_passive_observation_never_invents_jss_process_ownership(core, monkeypatch) -> None:
    monkeypatch.setattr(
        probes, "ollama",
        lambda _model: {
            "service": "ollama", "endpoint_reachable": True,
            "selected_model_present": True, "models": ["gemma3:latest"],
            "loaded_models": [], "loaded_models_state": "verified",
            "generation_verified": False,
        },
    )
    job = core.probe("ollama", observe_only=True)
    assert job.done.wait(5) and job.state == "succeeded"
    events = [event[2] for event in list(core.events.queue)
              if event[0] == "probe:ollama" and event[1] == "probe"]
    assert events[-1]["jss_owned_process"] is False
    assert events[-1]["monitor_only"] is True


def test_services_page_start_delegates_to_unique_ollama_controller(core, monkeypatch) -> None:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication
    from tools.jazn_run_studio.window import Window

    app = QApplication.instance() or QApplication([])
    window = Window(core, smoke=True)
    seen = []
    monkeypatch.setattr(core, "ensure_ollama",
                        lambda: SimpleNamespace(key="probe:ollama"))
    monkeypatch.setattr(core, "start_service",
                        lambda *_args: pytest.fail("double-spawn"))
    monkeypatch.setattr(window, "show_log", lambda key: seen.append(key))
    window.service("ollama", "start")
    assert seen == ["probe:ollama"]
    window.close()
    app.processEvents()


def test_readonly_monitor_displays_loaded_models_without_claiming_generation() -> None:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication, QWidget
    from tools.jazn_run_studio.service_status_dialog import ServiceStatusDialog

    app = QApplication.instance() or QApplication([])
    host = QWidget()
    panel = ServiceStatusDialog(host, lambda: pytest.fail("no implicit probe"))
    panel.observe("probe:ollama", "probe", {
        "service": "ollama", "endpoint_reachable": True,
        "selected_model_present": True,
        "models": ["gemma3:latest"],
        "loaded_models_state": "verified", "loaded_models": ["gemma3:latest"],
        "jss_owned_process": False, "generation_verified": False,
    })
    caption = panel.indicators["ollama"][1].text()
    assert "Niezweryfikowany" in caption
    assert "w pamięci: gemma3:latest" in caption
    assert "proces nieprzejęty przez JSS" in caption
    assert not panel.monitor_timer.isActive()
    panel.close()
    host.close()
