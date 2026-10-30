"""Real isolated regression planning; resume never replays a live request."""
import sys

import pytest
pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication

from tools.jazn_run_studio.tpa_engine import TPARunner
from tools.jazn_run_studio.tpa_plan_runner import TPAPlanRunner
from tools.jazn_run_studio.tpa_execution_plan import PlanStore, build_plan
from tests.test_jazn_tpa_execution_qt import wait_until
from tests.test_tpa_2_sources import repo


def test_real_regression_plan_preserves_source_and_restart_history(repo):
    app = QApplication.instance() or QApplication([])
    runner = TPARunner(repo, sys.executable)
    plan_runner = TPAPlanRunner(runner)
    plan_runner.start(("smoke-isolation",), source={"kind": "master", "value": ""})
    wait_until(lambda: not plan_runner.active, timeout=30)
    assert plan_runner.plan is not None
    assert plan_runner.plan["status"] == "COMPLETED"
    node = plan_runner.plan["tasks"][0]
    assert node["status"] == "PASS" and node["run_id"]
    assert plan_runner.plan["source_copy"]
    restored = PlanStore(runner.store).load(plan_runner.plan["plan_id"])
    assert restored["tasks"][0]["status"] == "PASS"
    assert runner.store.load(node["run_id"])["results"][0]["full_gate"] == "NOT_RUN"
    app.processEvents()


def test_resume_does_not_start_new_live_request_for_interrupted_node(repo, monkeypatch):
    app = QApplication.instance() or QApplication([])
    runner = TPARunner(repo, sys.executable)
    plans = TPAPlanRunner(runner)
    plan = build_plan(("chat-resume",), {"kind": "master", "value": ""}, "synthetic-model")
    for node in plan["tasks"]:
        node["status"] = "PASS"
    plan["tasks"][-1]["status"] = "RUNNING"
    plans.store.save(plan)
    monkeypatch.setattr(runner, "start_selection", lambda *_a, **_k: pytest.fail("must not replay a live turn"))
    plans.resume(plan["plan_id"])
    assert plans.plan is not None
    assert not plans.active
    assert plans.plan["tasks"][-1]["status"] == "INTERRUPTED"
    assert "request_id" in plans.plan["tasks"][-1]["reason"]
    app.processEvents()
