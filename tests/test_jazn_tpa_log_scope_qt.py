"""Completed logs stay immutable while another real test process writes output."""
from pathlib import Path
import sys
import pytest
pytest.importorskip("PySide6")
from tools.jazn_run_studio.tpa_view import TPAPanel
from tools.jazn_run_studio.tpa_reports import readable_report
from tests.test_jazn_tpa_execution_qt import system, wait_until


def test_log_button_keeps_selected_completed_test_separate_from_live_output(system):
    root, _ = system
    (root / "tests/test_jazn_system_root_config.py").write_text(
        "import time\ndef test_second():\n time.sleep(1)\n print('SECOND_TEST_ONLY')\n", encoding="utf-8")
    panel = TPAPanel(root, python=sys.executable)
    panel.start(("smoke-isolation", "config-persistence"))
    wait_until(lambda: panel.runner.index == 1 and panel.runner.phase == "tests")
    panel.table.selectRow(5)
    panel.show_log()
    first = panel.auto_log.toPlainText()
    assert "test_synthetic" in first
    wait_until(lambda: not panel.runner.active)
    assert panel.auto_log.toPlainText() == first
    panel.table.selectRow(6)
    panel.show_log()
    assert "SECOND_TEST_ONLY" in panel.auto_log.toPlainText()
    panel.close()


def test_coverage_map_json_and_readable_report_agree_with_executed_scope(system):
    root, _ = system
    panel = TPAPanel(root, python=sys.executable)
    panel.start(("smoke-isolation",))
    wait_until(lambda: not panel.runner.active)
    assert panel.report is not None
    loaded = panel.runner.store.load(panel.report["run_id"])
    entries = {c["id"]: c for c in loaded["coverage_map"]}
    assert entries["smoke-isolation"]["execution_status"] == "PASS"
    assert entries["smoke-isolation"]["full_gate"] == "NOT_RUN"
    assert entries["ollama-two-turns"]["execution_status"] == "NOT_RUN"
    assert "Wykonanie: PASS" in readable_report(loaded)
    panel.close()
