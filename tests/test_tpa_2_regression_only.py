"""Regression-only TPA planning never schedules a live Ollama/daemon phase."""
import json

import pytest

from tools.jazn_run_studio.tpa_catalog import execution_map
from tools.jazn_run_studio.tpa_execution_plan import LIVE_ORDER, PlanStore, build_plan
from tests.test_tpa_2_current_state import store


SOURCE = {"kind": "master", "value": ""}


def test_full_catalog_regression_only_has_22_subtests_and_no_live():
    plan = build_plan(tuple(row["id"] for row in execution_map()), SOURCE, include_live=False)
    assert len(plan["tasks"]) == 22
    assert plan["regression_only"] is True
    assert all(node["execution"] == "regression" for node in plan["tasks"])
    assert not any(node["id"].startswith("live:") for node in plan["tasks"])


def test_explicit_live_mode_keeps_canonical_dependencies():
    plan = build_plan(("daemon-restart",), SOURCE, include_live=True)
    assert plan["regression_only"] is False
    assert [node["case_id"] for node in plan["tasks"] if node["execution"] == "live"] == list(LIVE_ORDER)


def test_regression_only_plan_is_durable_and_resumes_without_live(store):
    plans = PlanStore(store)
    plan = build_plan(("ollama-two-turns", "smoke-isolation"), SOURCE, include_live=False)
    plans.save(plan)
    plan["tasks"][0]["status"] = "PASS"
    plans.save(plan)
    restored = PlanStore(store).load(plan["plan_id"])
    assert restored["regression_only"] is True
    assert all(node["execution"] == "regression" for node in restored["tasks"])
    assert restored["tasks"][0]["status"] == "PASS"


def test_tampered_plan_mode_cannot_smuggle_in_live_tasks(store):
    plans = PlanStore(store)
    plan = build_plan(("daemon-restart",), SOURCE, include_live=True)
    plans.save(plan)
    path = next(plans.folder(plan["plan_id"]).glob("checkpoint-*.json"))
    damaged = json.loads(path.read_text(encoding="utf-8"))
    damaged["regression_only"] = True
    path.write_text(json.dumps(damaged), encoding="utf-8")
    before = path.read_bytes()
    with pytest.raises(ValueError, match="zależności"):
        plans.load(plan["plan_id"])
    assert path.read_bytes() == before
