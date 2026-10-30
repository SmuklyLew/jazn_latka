"""Operator evidence follows the tested source, not the Studio installation."""
import json
from pathlib import Path
import sys

import pytest
pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication

from tools.jazn_run_studio.tpa_engine import TPARunner
from tools.jazn_run_studio.tpa_guidance import record_observation
from tests.test_jazn_tpa_execution_qt import wait_until
from tests.test_tpa_2_sources import repo, command


def test_observation_is_bound_to_verified_copy_even_if_studio_version_changes(repo):
    app = QApplication.instance() or QApplication([])
    # The selected regression has a real synthetic testcase and valid JUnit.
    (repo / "tests/test_jazn_system_root_config.py").write_text("def test_config(): assert True\n", encoding="utf-8")
    command(repo, "add", ".")
    command(repo, "commit", "-m", "synthetic config test")
    runner = TPARunner(repo, sys.executable)
    runner.start_selection(("config-persistence",), source_kind="master")
    wait_until(lambda: not runner.active, timeout=30)
    assert runner.report is not None
    report = runner.report
    row = report["results"][0]
    assert row["status"] == "PASS"
    (repo / "latka_jazn/version.py").write_text('PACKAGE_VERSION="9.9.9"', encoding="utf-8")
    with pytest.raises(ValueError, match="SHA"):
        record_observation(runner.store, report, "config-persistence", [0, 1, 2, 3], "observed", [row["junit"]], "PASS")
    source = Path(report["environment"]["execution_root"])
    runner.check_ready(source_root=source)
    wait_until(lambda: not runner.active)
    observation = record_observation(runner.store, report, "config-persistence", [0, 1, 2, 3], "observed",
                                     [row["junit"]], "PASS", verified_source=runner.probe["source"])
    assert observation["run_id"] == report["run_id"]
    assert observation["source"]["version"] != "9.9.9"
    assert report["results"][0]["full_gate"] == "PASS"
    app.processEvents()
