from __future__ import annotations

from pathlib import Path
from typing import Callable

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


@pytest.fixture
def stage05_public_context(monkeypatch: pytest.MonkeyPatch) -> Callable[[Path, str, str | None], None]:
    """Synthetic explicit owner binding and optional real durable admission."""
    import json
    from latka_jazn.config import JaznConfig
    from latka_jazn.core import runtime_daemon as daemon
    from latka_jazn.core.admission_owner_context import (
        PRIVATE_CONTEXT_OWNER_FILE, PRIVATE_CONTEXT_OWNER_SCHEMA, public_owner_digest,
    )

    def bind(root: Path, subject: str, request_id: str | None) -> None:
        owner = public_owner_digest(subject)
        path = root / PRIVATE_CONTEXT_OWNER_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            "schema_version": PRIVATE_CONTEXT_OWNER_SCHEMA, "owner_sha256": owner,
            "existing_shared_context_reviewed": True,
        }), encoding="utf-8")
        if request_id is None:
            return
        server = daemon.JaznDaemonServer(
            ("127.0.0.1", 0), daemon.JaznDaemonHandler,
            config=JaznConfig(root=root, memory_mode="off"),
            marker_path=daemon.resolve_active_runtime_marker_path(root),
            hard_worker_process_isolation=False,
        )
        monkeypatch.setattr(server, "start_chat_worker", lambda: None)
        monkeypatch.setattr(server, "start_chat_watchdog", lambda: None)
        try:
            job, created, error = server.submit_chat_job(
                request_id=request_id, user_text="synthetic", session_id="synthetic",
                input_field="message", no_carryover=False, client="synthetic",
                admission_owner_sha256=owner,
            )
            assert job is not None and created and error is None
        finally:
            server.close_sessions()
            server.server_close()

    return bind
