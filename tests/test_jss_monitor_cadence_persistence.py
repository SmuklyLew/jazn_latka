"""Isolated service-monitor scheduling, persistence and Qt lifecycle contracts."""
from dataclasses import replace
from types import SimpleNamespace
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
from tools.jazn_run_studio.core import Settings, StudioError, load_settings, save_settings
from tools.jazn_run_studio.service_monitor import ServiceMonitor

@pytest.mark.parametrize("seconds", ["1", "10", "30", "60"])
def test_interval_roundtrip(tmp_path, monkeypatch, seconds):
    monkeypatch.setenv("JAZN_STUDIO_ACCEPTANCE_PROFILE", "isolated")
    monkeypatch.setenv("JAZN_OPERATOR_STATE_ROOT", str(tmp_path / "operator"))
    settings = Settings.validate({"service_refresh_seconds": seconds})
    digest = save_settings(tmp_path, settings, None)
    assert load_settings(tmp_path) == (settings, digest)

@pytest.mark.parametrize("value", ["0", "5", "-1", "10.0", 10, None])
def test_invalid_cadence_rejected(value):
    with pytest.raises(StudioError):
        Settings.validate({"service_refresh_seconds": value})

def test_poll_isolates_errors_and_throttles_system_checks():
    calls = []
    now = [0.0]
    def action(key):
        calls.append(key)
        if key == "status":
            raise StudioError("busy")
    core = SimpleNamespace(closed=False, settings=Settings(service_refresh_seconds="1"),
        start_action=action, probe=lambda key, **kw: calls.append((key, kw)),
        emit=lambda *args: None)
    monitor = ServiceMonitor(core, lambda: now[0])
    for second in range(11):
        now[0] = float(second)
        monitor.poll()
    assert calls.count("status") == calls.count("supervisor") == 2
    assert calls.count(("ollama", {"observe_only": True})) == 11
    core.closed = True
    previous = len(calls)
    monitor.poll()
    assert len(calls) == previous

def test_dialog_open_close_and_failed_save():
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication, QWidget
    from tools.jazn_run_studio.service_status_dialog import ServiceStatusDialog
    app = QApplication.instance() or QApplication([])
    host = QWidget()
    calls = []
    def reject(seconds):
        raise OSError("readonly")
    panel = ServiceStatusDialog(host, lambda: calls.append(1), save_interval=reject)
    assert not panel.timer.isActive() and not panel.monitor_timer.isActive()
    panel.show()
    app.processEvents()
    assert calls == [1]
    assert panel.timer.isActive() and panel.monitor_timer.isActive()
    panel.refresh_interval.setCurrentIndex(0)
    assert panel.refresh_interval.currentData() == 10000
    assert panel.monitor_timer.interval() == 10000
    assert panel.persistence_status.text()
    panel.close()
    assert not panel.timer.isActive() and not panel.monitor_timer.isActive()
    panel._monitor_once()
    assert calls == [1]
    panel.show()
    assert calls == [1, 1]
    panel.close()
    host.close()
