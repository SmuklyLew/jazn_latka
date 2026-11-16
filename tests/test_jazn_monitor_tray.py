"""Tray lifecycle regression: window may hide, but Jaźń remains untouched."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QSystemTrayIcon
from tools.jazn_monitor import window as window_module


@pytest.fixture(scope="module")
def app():
    existing = QApplication.instance()
    application = existing or QApplication([])
    yield application


def test_no_tray_keeps_minimized_window_recoverable(monkeypatch, app):
    monkeypatch.setattr(window_module, "_system_tray_available", lambda: False)
    win = window_module.MonitorWindow(None, 8787, 11434, smoke=True)
    assert win._tray_icon is None
    assert not win.tray_button.isEnabled()
    win.show()
    win.showMinimized()
    app.processEvents()
    assert win.isVisible()  # Minimized in taskbar, not hidden without a tray.
    win.close()


def test_tray_minimize_restore_and_exit_are_observer_only(monkeypatch, app):
    monkeypatch.setattr(window_module, "_system_tray_available", lambda: True)
    win = window_module.MonitorWindow(None, 8787, 11434, smoke=True)
    assert win._tray_icon is not None
    assert win._tray_icon.isVisible()
    menu = win._tray_menu
    assert menu is not None
    assert [action.text() for action in menu.actions() if not action.isSeparator()] == [
        "Pokaż Jaźń Monitor", "Zakończ monitor"]
    win.show()
    app.processEvents()
    win.showMinimized()
    app.processEvents()
    # Covers deferred hide as well as direct invocation on headless Qt.
    win._hide_minimized_window()
    assert not win.isVisible()
    win._on_tray_activated(QSystemTrayIcon.ActivationReason.DoubleClick)
    app.processEvents()
    assert win.isVisible() and not win.isMinimized()
    win.showMinimized()
    win._hide_minimized_window()
    menu.actions()[0].trigger()
    app.processEvents()
    assert win.isVisible()
    menu.actions()[-1].trigger()
    app.processEvents()
    assert win._closing
    assert not win._tray_icon.isVisible()
