"""Queued I/O retains its QRunnable until the Qt GUI receives completion.

The JSS persistence lane must never silently lose callbacks as QRunnable
ownership moves between the global thread pool and Python/Qt.
"""
from __future__ import annotations

import threading
import time

import pytest

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication

from tools.jazn_run_studio.tpa_io import SerialIO, _Work


def _pump_until(predicate, *, seconds: float = 12) -> None:
    end = time.monotonic() + seconds
    while not predicate() and time.monotonic() < end:
        QApplication.processEvents()
        time.sleep(0.005)
    assert predicate(), "queued persistence callback missing"


def test_runnable_is_application_owned_until_queued_delivery() -> None:
    worker = _Work(lambda: "synthetic")
    assert worker.autoDelete() is False


def test_serial_durable_callbacks_are_ordered_and_return_to_gui_thread() -> None:
    app = QApplication.instance() or QApplication([])
    gui_thread = threading.get_ident()
    lane = SerialIO(app)
    saved = []
    errors = []

    for index in range(24):
        lane.submit(
            lambda i=index: (i, threading.get_ident()),
            lambda item: saved.append((threading.get_ident(), item)),
            errors.append,
        )

    _pump_until(lambda: not lane.pending)
    assert not errors
    assert [item[1][0] for item in saved] == list(range(24))
    assert all(item[0] == gui_thread and item[1][1] != gui_thread for item in saved)


def test_failed_durable_write_aborts_dependent_callbacks() -> None:
    app = QApplication.instance() or QApplication([])
    lane = SerialIO(app)
    completed = []
    errors = []

    def fail() -> None:
        raise OSError("synthetic disk failure")

    lane.submit(fail, completed.append, errors.append)
    lane.submit(lambda: "must not run", completed.append, errors.append)
    _pump_until(lambda: not lane.pending)

    assert completed == []
    assert errors == ["OSError"]
