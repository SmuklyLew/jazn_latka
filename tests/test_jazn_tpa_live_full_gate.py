"""TPA live subprocess success must not manufacture operator full-gate approval."""
import sys
import time

import pytest

pytest.importorskip("PySide6")
from PySide6.QtCore import QCoreApplication
from tools.jazn_run_studio.tpa_catalog import scenario
from tools.jazn_run_studio.tpa_engine import TPARunner
from tools.jazn_run_studio.tpa_guidance import record_observation
from tools.jazn_run_studio.tpa_reports import safe_child


@pytest.mark.parametrize("exit_code, expected", [(0, "PASS"), (1, "FAIL")])
def test_live_result_requires_zero_child_exit_and_separate_human_gate(tmp_path, monkeypatch, exit_code, expected):
    app = QCoreApplication.instance() or QCoreApplication([])
    root = tmp_path / "SYSTEM"
    (root / "latka_jazn").mkdir(parents=True)
    (root / "latka_jazn/version.py").write_text('PACKAGE_VERSION="1.2.3"\n', encoding="utf-8")
    monkeypatch.setenv("JAZN_OPERATOR_STATE_ROOT", str(tmp_path / "operator"))
    runner = TPARunner(root, sys.executable)
    report = runner.store.create(("ollama-two-turns",), sys.executable, {"memory_mode": "off"})
    report["execution"] = "live"
    runner.report = report
    runner.index = 0
    runner.started = time.monotonic()
    runner.reason = ""
    runner.live_exit_code = exit_code
    turns = [{"accepted": True, "request_id": f"request-{n}", "turn_id": f"turn-{n}",
              "trace_id": f"trace-{n}", "text": "Synthetic accepted text"} for n in range(2)]
    runner.live_result = {"status": "PASS", "reason": "Synthetic accepted turn result", "evidence": {
        "identity": {"instance_id": "synthetic-owned", "root_matches": True, "version_matches": True,
                     "process_identity_confirmed": True, "endpoint_identity_matches": True, "heartbeat_fresh": True},
        "session_id": "synthetic-session", "turns": turns,
        "displayed_request_ids": [t["request_id"] for t in turns]}}
    runner.cleanup_result = {"ok": True}
    runner.log_name = "ollama-two-turns.log"
    runner.buffer = "Synthetic test evidence, no real service called.\n"
    runner._live_done(0)

    saved = runner.store.load(report["run_id"])
    assert saved["results"][0]["status"] == expected
    assert saved["results"][0]["full_gate"] == "NOT_RUN"
    assert saved["results"][0]["cleanup_exit_code"] == 0

    if exit_code == 0:
        # Explicit human checklist and owned evidence, not child status, promote full_gate.
        report["finished_utc"] = "synthetic-finished"
        proof = "proof-synthetic.txt"
        safe_child(runner.store.folder(report["run_id"]), proof).write_text(
            "Synthetic operator test observation.", encoding="utf-8"
        )
        report["artifacts"].append(proof)
        runner.store.save(report)
        record_observation(
            runner.store,
            report,
            "ollama-two-turns",
            list(range(len(scenario("ollama-two-turns")["guide"]))),
            "Synthetic review of the completed run",
            [proof],
            "PASS",
        )
        assert runner.store.load(report["run_id"])["results"][0]["full_gate"] == "PASS"
    del app
