"""Actual owned queue and durability barriers under blocked/failing I/O."""
from pathlib import Path
from copy import deepcopy
import sys
import tempfile
import threading

import pytest
pytest.importorskip("PySide6")
from PySide6.QtCore import QTimer
from tools.jazn_run_studio.tpa_engine import TPARunner
from tools.jazn_run_studio.tpa_io import SerialIO
from tests.test_jazn_tpa_execution_qt import system, wait_until


def hold_first_save(runner, monkeypatch, *, final=False):
    entered, release = threading.Event(), threading.Event()
    original = runner.store.save
    threads = []
    def save(report):
        threads.append(threading.get_ident())
        if not entered.is_set() and (bool(report.get("finished_utc")) if final else True):
            entered.set()
            if not release.wait(10):
                raise TimeoutError("Synthetic write barrier was not released")
        original(report)
    monkeypatch.setattr(runner.store, "save", save)
    return entered, release, threads


def test_initial_write_does_not_block_gui_or_launch_before_durability(system, monkeypatch):
    root, _ = system
    runner = TPARunner(root, sys.executable)
    entered, release, threads = hold_first_save(runner, monkeypatch)
    launched, beats, callbacks = [], [], []
    gui_thread = threading.get_ident()
    original_start = runner.process.start
    def start(python, args):
        assert not runner.persistence_pending
        assert runner.report is not None
        saved = runner.store.load(runner.report["run_id"])
        assert (runner.store.folder(saved["run_id"]) / "manifest.json").is_file()
        if runner.phase == "tests":
            assert saved["results"][0]["status"] == "RUNNING"
        launched.append(runner.phase)
        original_start(python, args)
    monkeypatch.setattr(runner.process, "start", start)
    runner.completed.connect(lambda _report: callbacks.append(threading.get_ident()))
    timer = QTimer()
    timer.timeout.connect(lambda: beats.append(1))
    timer.start(10)
    runner.start_selection(("smoke-isolation",))
    try:
        wait_until(entered.is_set)
        count = len(beats)
        wait_until(lambda: len(beats) >= count + 3)
        assert runner.active and not launched
        assert runner.persistence_pending
    finally:
        release.set()
        wait_until(lambda: not runner.active)
        timer.stop()
    assert launched == ["preflight", "tests"]
    assert threads and all(thread != gui_thread for thread in threads)
    assert callbacks == [gui_thread]
    assert runner.report is not None and runner.report["results"][0]["status"] == "PASS"


def test_cancel_during_initial_write_never_starts_a_child(system, monkeypatch):
    root, _ = system
    runner = TPARunner(root, sys.executable)
    entered, release, _ = hold_first_save(runner, monkeypatch)
    starts = []
    monkeypatch.setattr(runner.process, "start", lambda *_args: starts.append(1))
    runner.start_selection(("smoke-isolation", "config-persistence"))
    try:
        wait_until(entered.is_set)
        runner.stop()
        assert runner.active and runner.persistence_pending
    finally:
        release.set()
        wait_until(lambda: not runner.active)
    assert not starts
    assert runner.report is not None
    saved = runner.store.load(runner.report["run_id"])
    assert [row["status"] for row in saved["results"]] == ["CANCELLED", "CANCELLED"]


def test_failed_running_save_prevents_test_launch_and_preserves_prior_snapshot(system, monkeypatch):
    root, _ = system
    runner = TPARunner(root, sys.executable)
    original_save, original_start = runner.store.save, runner.process.start
    starts = []
    def save(report):
        if report["results"][0]["status"] == "RUNNING":
            raise OSError("Synthetic full disk")
        original_save(report)
    def start(python, args):
        starts.append(runner.phase)
        original_start(python, args)
    monkeypatch.setattr(runner.store, "save", save)
    monkeypatch.setattr(runner.process, "start", start)
    runner.start_selection(("smoke-isolation",))
    wait_until(lambda: not runner.active)
    assert starts == ["preflight"]
    assert runner.report is not None and runner.report["persistence_error"]
    assert runner.report["results"][0]["status"] == "CANCELLED"
    saved = runner.store.load(runner.report["run_id"])
    assert not any(row["status"] == "PASS" for row in saved["results"])
    assert runner.process.processId() == 0


def test_completed_waits_for_final_snapshot_and_owned_cleanup(system, monkeypatch):
    root, _ = system
    runner = TPARunner(root, sys.executable)
    entered, release, threads = hold_first_save(runner, monkeypatch, final=True)
    completed, temp_paths = [], []
    original_start = runner.process.start
    def start(python, args):
        assert runner.temp is not None
        temp_paths.append(Path(runner.temp.name))
        original_start(python, args)
    monkeypatch.setattr(runner.process, "start", start)
    runner.completed.connect(completed.append)
    runner.start_selection(("smoke-isolation",))
    try:
        wait_until(entered.is_set)
        assert runner.active and not completed
        assert temp_paths and all(not path.exists() for path in temp_paths)
    finally:
        release.set()
        wait_until(lambda: not runner.active)
    assert len(completed) == 1
    assert runner.report is not None
    saved = runner.store.load(runner.report["run_id"])
    assert saved["finished_utc"] and saved["results"][0]["status"] == "PASS"
    assert all(thread != threading.get_ident() for thread in threads)


def test_serial_lane_overflow_aborts_dependent_callbacks(system):
    _, app = system
    lane = SerialIO(app)
    entered, release = threading.Event(), threading.Event()
    done, failed = [], []
    def operation():
        entered.set()
        if not release.wait(10):
            raise TimeoutError("Synthetic barrier")
        return 1
    lane.submit(operation, done.append, failed.append)
    try:
        wait_until(entered.is_set)
        for _ in range(65):
            lane.submit(lambda: 2, done.append, failed.append)
    finally:
        release.set()
        wait_until(lambda: not lane.pending)
    assert done == [] and failed == ["EvidenceQueueLimit"]


def test_readiness_cleanup_failure_does_not_relabel_previous_report(system):
    root, _ = system
    runner = TPARunner(root, sys.executable)
    runner.report = runner.store.create(("smoke-isolation",), sys.executable, {})
    previous = deepcopy(runner.report)
    messages, completed = [], []
    runner.progress.connect(messages.append)
    runner.completed.connect(completed.append)
    runner.active, runner.phase, runner._next_after_probe = True, "preflight", False
    runner._persistence_failed("PermissionError")
    assert not runner.active and not completed
    assert runner.report == previous and not runner.persistence_error
    assert messages and "PermissionError" in messages[-1]


def test_cleanup_failure_is_explicit_after_write_failure(system, monkeypatch):
    root, _ = system
    runner = TPARunner(root, sys.executable)
    runner.report = runner.store.create(("smoke-isolation",), sys.executable, {})
    temporary = tempfile.TemporaryDirectory(dir=root.parent)
    original_cleanup = temporary.cleanup
    def refuse_cleanup():
        raise PermissionError("Synthetic owned cleanup refusal")
    monkeypatch.setattr(temporary, "cleanup", refuse_cleanup)
    runner.temp = temporary
    runner.active, runner.phase = True, "persisting"
    try:
        runner._persistence_failed("OSError")
        wait_until(lambda: not runner.active)
        assert runner.report["persistence_error"] and "PermissionError" in runner.report["cleanup_error"]
        assert runner.report["results"][0]["status"] == "CANCELLED"
        assert Path(temporary.name).is_dir()
    finally:
        original_cleanup()
