"""Run real QProcess/pytest regression queue without inheriting TPA checkpoints.

The fixtures are synthetic and MEMORY stays disabled. No real daemon, account
or MEMORY database is opened, and a result cannot imply a live acceptance PASS.
"""
from __future__ import annotations

import sys

import pytest

pytest.importorskip("PySide6")
from PySide6.QtCore import QProcessEnvironment

from tools.jazn_run_studio.tpa_catalog import scenario
from tools.jazn_run_studio.tpa_engine import TPARunner, regression_environment
from tests.test_jazn_tpa_execution_qt import system, wait_until  # noqa: F401


REGRESSION_CASES = (
    "chat-reconnect",
    "config-persistence",
    "studio-memory-rebuild",
    "studio-python-runtime",
)

# The same four case IDs which failed in the operator's Windows TPA run.
CHECK_CHILD_ENV = """import os
def test_tpa_regression_child_environment():
    assert os.environ.get("JAZN_MEMORY_MODE") == "off"
    assert os.environ.get("JAZN_MEMORY_ROOT")
    assert os.environ.get("JAZN_RUNTIME_WORKSPACE_DIR")
    for key in (
        "JAZN_STUDIO_ACCEPTANCE_PROFILE",
        "JAZN_OPERATOR_STATE_ROOT",
        "JAZN_MEMORY_REBUILD_SETTINGS",
        "JAZN_MEMORY_REBUILD_PROJECTS",
    ):
        assert key not in os.environ, key
"""


def test_actual_tpa_queue_isolates_all_four_regression_scenarios(system) -> None:
    root, _app = system
    for case_id in REGRESSION_CASES:
        for relative in scenario(case_id)["files"]:
            file = root / relative
            file.write_text(CHECK_CHILD_ENV, encoding="utf-8")

    runner = TPARunner(root, sys.executable)
    runner.start_selection(REGRESSION_CASES, execution="regression")
    wait_until(lambda: not runner.active, timeout=60)

    assert runner.report is not None
    assert [row["case_id"] for row in runner.report["results"]] == list(REGRESSION_CASES)
    assert [row["status"] for row in runner.report["results"]] == ["PASS"] * 4
    assert all(row["full_gate"] == "NOT_RUN" for row in runner.report["results"])
    saved = runner.store.load(runner.report["run_id"])
    assert saved["summary"]["counts"] == {"PASS": 4}
    assert saved["source"]["git_sha"] is None


def test_regression_environment_rejects_enabled_memory_or_missing_isolation() -> None:
    unsafe = QProcessEnvironment()
    unsafe.insert("JAZN_MEMORY_MODE", "required")
    unsafe.insert("JAZN_RUNTIME_WORKSPACE_DIR", "synthetic")
    unsafe.insert("JAZN_MEMORY_ROOT", "synthetic-memory")
    with pytest.raises(ValueError, match="wyłączonej MEMORY"):
        regression_environment(unsafe)

    unsafe.insert("JAZN_MEMORY_MODE", "off")
    unsafe.remove("JAZN_MEMORY_ROOT")
    with pytest.raises(ValueError, match="Brak izolowanego"):
        regression_environment(unsafe)
