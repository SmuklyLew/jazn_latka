"""One canonical Jaźń Monitor in JSS; no duplicate observer or runtime owner.

The standalone monitor's read-only snapshot is the sole source of service
status presentation; operator lifecycle stays in Controller.
"""
from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools.jazn_run_studio.monitor_bridge import (
    MAX_MONITOR_AGE_SECONDS, monitor_service, validated_snapshot,
    verified_daemon_pid,
)

SERVICES = {
    "Daemon Jaźni": {"state": "ready", "detail": "PID 2222 · świeży heartbeat"},
    "Runtime Core": {"state": "reachable", "detail": "Chat worker niezweryfikowany"},
    "Ollama": {"state": "reachable", "detail": "API odpowiada; bez generacji"},
    "MCP": {"state": "unknown", "detail": "Brak OAuth"},
    "Supervisor": {"state": "unknown", "detail": "Bez potwierdzenia właściciela"},
    "JSS": {"state": "unknown", "detail": "Lokalna aplikacja"},
    "MEMORY": {"state": "disabled", "detail": "MEMORY wyłączona"},
}


def report(root: Path) -> dict:
    return {
        "schema_version": "jazn_monitor_snapshot/v1",
        "observation_only": True,
        "selected_root": str(root.resolve()),
        "services": SERVICES,
        "observed_at_utc": "2026-11-21T07:00:00+00:00",
        "processes": {"items": [{
            "name": "Jaźń — Daemon", "pid": 2222,
            "evidence": "verified_instance",
        }]},
        "jobs": {"items": [], "finalization": {}},
        "finalization": {"state": "unknown"},
    }


def test_bridge_requires_current_root_and_read_only_schema(tmp_path: Path) -> None:
    good = report(tmp_path)
    assert validated_snapshot(good, tmp_path) is good
    for invalid in (
        {**good, "selected_root": str(tmp_path / "other")},
        {**good, "observation_only": False},
        {**good, "schema_version": "unknown"},
        {**good, "services": []},
    ):
        assert validated_snapshot(invalid, tmp_path) is None


def test_readiness_never_exceeds_monitor_evidence(tmp_path: Path) -> None:
    payload = report(tmp_path)
    assert monitor_service(payload, "ollama", age_seconds=0)[0] == "reachable"
    assert monitor_service(payload, "runtime", age_seconds=0)[0] == "reachable"
    assert monitor_service(payload, "memory", age_seconds=0)[0] == "disabled"
    assert monitor_service(payload, "cloudflare", age_seconds=0)[0] == "unknown"
    assert monitor_service(payload, "runtime", age_seconds=MAX_MONITOR_AGE_SECONDS + 1)[0] == "unknown"
    assert monitor_service(None, "ollama", age_seconds=None)[0] == "unknown"
    assert verified_daemon_pid(payload, age_seconds=1) == 2222
    assert verified_daemon_pid(payload, age_seconds=60) is None
    payload["processes"]["items"][0]["evidence"] = "pid_only"
    assert verified_daemon_pid(payload, age_seconds=1) is None


def test_bridge_rejects_unrecognized_status_instead_of_ready(tmp_path: Path) -> None:
    payload = report(tmp_path)
    payload["services"]["Runtime Core"] = {"state": "done", "detail": "untrusted"}
    assert monitor_service(payload, "runtime", age_seconds=1)[0] == "unknown"


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def test_jss_uses_new_monitor_window_and_one_snapshot_without_spawning(monkeypatch, tmp_path: Path) -> None:
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication
    from tools.jazn_monitor.window import MonitorWindow
    from tools.jazn_run_studio.core import Controller, Settings
    from tools.jazn_run_studio.window import Window

    app = QApplication.instance() or QApplication([])
    (tmp_path / "latka_jazn").mkdir()
    for marker in ("run.py", "main.py", "latka_jazn/version.py"):
        (tmp_path / marker).touch()
    core = Controller(tmp_path, Settings(theme="dark", service_refresh_seconds="30"))
    window = Window(core, smoke=True)
    try:
        monkeypatch.setattr(core, "start_action",
                            lambda *_args: pytest.fail("opening monitor cannot start runtime"))
        monkeypatch.setattr(core, "start_service",
                            lambda *_args: pytest.fail("opening monitor cannot start Ollama"))
        window.open_service_status()
        monitor = window.monitor_window
        assert isinstance(monitor, MonitorWindow)
        assert monitor.integrated
        assert monitor.parent() is window
        assert monitor._tray_icon is None
        assert monitor.root_field.isReadOnly()
        assert monitor.timer.interval() == 30000
        assert monitor.tabs.count() == 4
        assert not monitor._smoke is False  # smoke prevents automatic probes

        payload = report(tmp_path)
        monitor.apply_snapshot(payload)
        assert window.monitor_report == payload
        assert monitor.table.item(1, 1).text() == "DOSTĘPNY"
        service_row = window.service_rows["runtime"]
        assert "DOSTĘPNY" in window.statuses["runtime"].text()
        assert window.services_table.item(service_row, 4).text() == "DOSTĘPNY"
        assert window.services_table.item(service_row, 2).text() == "2222"
        assert "NIEZWERYFIKOWANY" in window.statuses["cloudflare"].text()
        assert window.models_summary.text().startswith("Ollama: DOSTĘPNY")

        window.accept_monitor_snapshot({**payload, "selected_root": str(tmp_path / "elsewhere")})
        assert window.monitor_report == payload
        window.monitor_observed_at -= MAX_MONITOR_AGE_SECONDS + 2
        window.refresh_service_table()
        assert "NIEZWERYFIKOWANY" in window.statuses["runtime"].text()
        assert window.services_table.item(service_row, 2).text() == "—"

        monitor.close()
        assert not monitor.timer.isActive()
        assert not monitor._closing
        window.open_service_status()
        assert window.monitor_window is monitor
    finally:
        window.close()
        app.processEvents()


def test_monitor_integrated_ignores_root_retargeting(monkeypatch, tmp_path: Path) -> None:
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication
    from tools.jazn_monitor import window as module

    app = QApplication.instance() or QApplication([])
    widget = module.MonitorWindow(tmp_path, 8787, 11434, smoke=True, integrated=True)
    created = []

    class Signal:
        def connect(self, _callback):
            pass

    class Worker:
        observed = Signal()
        finished = Signal()

        def __init__(self, root, *_args):
            created.append(root)

        def start(self):
            pass

        def isRunning(self):
            return False

    try:
        monkeypatch.setattr(module, "ProbeThread", Worker)
        widget.root_field.setText(str(tmp_path / "other"))
        widget.refresh()
        assert created == [tmp_path.resolve()]
        widget.close()
    finally:
        app.processEvents()
