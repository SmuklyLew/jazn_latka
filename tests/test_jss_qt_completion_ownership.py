"""Regression: Qt senders outlive their queued completion slots.

A QRunnable must not be auto-deleted by QThreadPool while the receiving
widget/SerialIO still owns a Python wrapper. Sender deletion is deferred.
"""
from __future__ import annotations

import time
import weakref

import pytest

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication, QWidget
from shiboken6 import isValid

from tools.jazn_run_studio.tpa_io import SerialIO
from tools.jazn_run_studio.test_history_view import _ArchiveJob, _ReadHistory, TestHistoryPanel


def _wait_for(predicate) -> None:
    deadline = time.monotonic() + 10
    while not predicate() and time.monotonic() < deadline:
        QApplication.processEvents()
        time.sleep(0.005)
    assert predicate(), "Qt completion was not delivered"


def test_serial_completion_sender_survives_callback_dispatch() -> None:
    app = QApplication.instance() or QApplication(["jazn-qt-ownership-test"])
    host = QWidget()
    lane = SerialIO(host)
    was_valid: list[bool] = []
    failures: list[str] = []
    sender_refs: list[weakref.ReferenceType] = []

    def completed(value: str) -> None:
        assert value == "ok"
        sender = sender_refs[0]()
        was_valid.append(sender is not None and isValid(sender))

    lane.submit(lambda: "ok", completed, failures.append)
    assert lane.job is not None
    sender_refs.append(weakref.ref(lane.job.signals))
    _wait_for(lambda: not lane.pending)
    assert was_valid == [True]
    assert failures == []
    app.processEvents()
    host.close()
    host.deleteLater()
    app.processEvents()


def test_history_jobs_are_not_owned_by_threadpool() -> None:
    from pathlib import Path
    read = _ReadHistory(Path("."), Path("."))
    archive = _ArchiveJob("import", ())
    assert read.autoDelete() is False
    assert archive.autoDelete() is False


def test_history_panel_retains_worker_until_queued_completion_finishes(tmp_path) -> None:
    app = QApplication.instance() or QApplication(["jazn-qt-ownership-test"])
    panel = TestHistoryPanel(tmp_path)
    read = _ReadHistory(tmp_path, tmp_path)
    sender = weakref.ref(read.signals)
    panel.worker = read
    del read
    panel.loaded({
        "runs": [], "errors": [], "sha": None,
        "dirty": None, "base": tmp_path,
    })
    assert sender() is not None and isValid(sender())

    archive = _ArchiveJob("export", ())
    archive_sender = weakref.ref(archive.signals)
    panel.archive_worker = archive
    del archive
    panel.archive_completed({"error": "synthetic-only"})
    assert archive_sender() is not None and isValid(archive_sender())

    app.processEvents()
    panel.close()
    panel.deleteLater()
    app.processEvents()
