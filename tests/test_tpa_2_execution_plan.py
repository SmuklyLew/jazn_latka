"""Dependency order, immutable checkpoints and phase-specific timeouts."""
from copy import deepcopy
import json

import pytest

from tools.jazn_run_studio.tpa_execution_plan import (
    LIVE_ORDER, PHASE_TIMEOUTS, PhaseDeadline, PlanStore, blocked_dependencies, build_plan,
)
from tests.test_tpa_2_current_state import store

SOURCE = {"kind": "master", "value": ""}


def test_restart_cannot_bypass_live_or_regression_predecessors():
    plan = build_plan(("daemon-restart",), SOURCE)
    assert [n["case_id"] for n in plan["tasks"] if n["execution"] == "live"] == list(LIVE_ORDER)
    by_id = {n["id"]: n for n in plan["tasks"]}
    assert by_id["live:daemon-restart"]["depends_on"] == ["regression:daemon-restart", "live:chat-resume"]
    by_id["regression:gui-daemon"]["status"] = "FAIL"
    blocked_dependencies(plan)
    assert all(n["status"] == "BLOCKED" for n in plan["tasks"] if n["execution"] == "live")
    assert by_id["regression:ollama-two-turns"]["status"] == "QUEUED"


def test_pending_prerequisite_is_not_a_failure_and_live_cannot_count_as_full_acceptance():
    plan = build_plan(("ollama-two-turns",), SOURCE)
    blocked_dependencies(plan)
    assert all(n["status"] == "QUEUED" for n in plan["tasks"])
    assert not any(n.get("full_gate") == "PASS" for n in plan["tasks"])
    assert set(PHASE_TIMEOUTS) >= {"preflight", "start", "heartbeat", "readiness", "generation", "finalization", "restart", "cleanup", "gui", "operator"}


def test_phase_deadlines_do_not_time_out_a_human(monkeypatch):
    from tools.jazn_run_studio import tpa_execution_plan
    now = [1.0]
    monkeypatch.setattr(tpa_execution_plan.time, "monotonic", lambda: now[0])
    clock = PhaseDeadline()
    clock.enter("operator")
    now[0] += 100000
    clock.check()
    clock.enter("generation")
    now[0] += 121
    with pytest.raises(TimeoutError, match="generation"):
        clock.check()
    clock.enter("gui")
    now[0] += 121
    with pytest.raises(TimeoutError, match="gui"):
        clock.check()


def test_plan_checkpoints_survive_restart_without_overwriting_earlier_states(store):
    plans = PlanStore(store)
    plan = build_plan(("smoke-isolation",), SOURCE)
    plans.save(plan)
    first = {p.name: p.read_bytes() for p in plans.folder(plan["plan_id"]).glob("checkpoint-*.json")}
    plan["tasks"][0]["status"] = "PASS"
    plans.save(plan)
    restored = PlanStore(store).load(plan["plan_id"])
    assert restored["tasks"][0]["status"] == "PASS"
    assert all((plans.folder(plan["plan_id"]) / name).read_bytes() == raw for name, raw in first.items())


def test_tampered_dependency_checkpoint_is_refused_without_repairing_it(store):
    plans = PlanStore(store)
    plan = build_plan(("daemon-restart",), SOURCE)
    plans.save(plan)
    path = next(plans.folder(plan["plan_id"]).glob("checkpoint-*.json"))
    corrupt = json.loads(path.read_text(encoding="utf-8"))
    corrupt["tasks"][-1]["depends_on"] = []
    path.write_text(json.dumps(corrupt), encoding="utf-8")
    before = path.read_bytes()
    with pytest.raises(ValueError, match="zależności"):
        plans.load(plan["plan_id"])
    assert path.read_bytes() == before
