from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _isolate_runtime_workspace_for_each_test(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep each test's workspace inside its resolved SYSTEM ROOT.

    The V127.4 production resolver refuses external workspace overrides.
    Give every pytest case a unique ROOT-relative acceptance path so even
    subprocesses bound to the real checkout cannot adopt a live daemon or
    write to a shared workspace. Tests of legacy external roots explicitly
    remove or replace this override.
    """

    monkeypatch.setenv(
        "JAZN_RUNTIME_WORKSPACE_DIR",
        "$ROOT/.settings_local/acceptance/pytest_runtime_" + tmp_path.name,
    )


@pytest.fixture(scope="session", autouse=True)
def _qt_application_session_lifetime():
    """Retain one Qt GUI application until every GUI test has torn down.

    Several independent tests call QApplication.instance() or QApplication([])
    in local scopes. Without a session owner the first Python reference can
    disappear before other Qt objects and queued callbacks have been disposed.
    No Qt import or GUI startup occurs for CLI-only suites or on headless hosts
    without an explicitly available GUI backend.
    """
    import os
    import sys

    can_run_gui = bool(
        os.name == "nt" or os.environ.get("QT_QPA_PLATFORM")
        or os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")
    )
    if not can_run_gui or "PySide6.QtWidgets" not in sys.modules:
        yield
        return

    from PySide6.QtCore import QCoreApplication, QEvent, QThreadPool
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication(["jazn-pytest"])
    if not isinstance(app, QApplication):
        raise AssertionError("Qt test suite requires QApplication, not QCoreApplication")

    yield

    # A test may have completed while background report workers were still
    # returning from QRunnable.run(). Never destroy their QObject senders first.
    pool = QThreadPool.globalInstance()
    assert pool.waitForDone(10_000), "Qt worker threads still active at test teardown"
    app.processEvents()
    for widget in QApplication.topLevelWidgets():
        widget.hide()
        widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()
