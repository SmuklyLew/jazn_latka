"""Selected-source execution uses a real detached copy, not the active checkout."""
import sys

import pytest
pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication

from tools.jazn_run_studio.tpa_engine import TPARunner
from tests.test_jazn_tpa_execution_qt import wait_until
from tests.test_tpa_2_sources import repo, command


def test_real_source_preparation_and_child_test_are_persisted(repo):
    app = QApplication.instance() or QApplication([])
    runner = TPARunner(repo, sys.executable)
    original = command(repo, "rev-parse", "HEAD")
    runner.start_selection(("smoke-isolation",), source_kind="master")
    wait_until(lambda: not runner.active, timeout=30)
    assert runner.report is not None
    report = runner.store.load(runner.report["run_id"])
    assert report["source"]["git_sha"] == original
    assert report["source"]["source_kind"] == "master"
    assert report["results"][0]["status"] == "PASS"
    assert runner.execution_root != repo
    assert command(runner.execution_root, "branch", "--show-current") == ""
    assert command(repo, "rev-parse", "HEAD") == original
    assert not (repo / "workspace_runtime").exists()
    app.processEvents()


def test_unresolvable_source_is_blocked_without_testing_active_checkout(repo):
    app = QApplication.instance() or QApplication([])
    runner = TPARunner(repo, sys.executable)
    runner.start_selection(("smoke-isolation",), source_kind="branch", source_value="does-not-exist")
    wait_until(lambda: not runner.active, timeout=30)
    assert runner.report is not None
    row = runner.report["results"][0]
    assert row["status"] == "BLOCKED"
    assert not row.get("command")
    assert runner.report["source_preparation_error"]
    app.processEvents()
