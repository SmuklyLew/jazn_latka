"""TPA checkpoint regression: secret masking must not corrupt control state."""
import json

import pytest

from tools.jazn_run_studio.core import Redactor
from tools.jazn_run_studio.tpa_execution_plan import PlanStore, build_plan
from tools.jazn_run_studio.tpa_reports import RunStore
from tests.test_tpa_2_current_state import store


def test_checkpoint_survives_secret_collision_and_changed_restart_environment(store, monkeypatch):
    # Synthetic secrets deliberately equal the absolute SYSTEM path and a
    # public source-kind enum. No private material is used in this test.
    monkeypatch.setenv("JAZN_TPA_TEST_TOKEN", str(store.root))
    monkeypatch.setenv("JAZN_TPA_TEST_SECRET", "master")
    store.redactor = Redactor()
    plans = PlanStore(store)
    plan = build_plan(("smoke-isolation",), {"kind": "master", "value": ""})
    plans.save(plan)
    path = next(plans.folder(plan["plan_id"]).glob("checkpoint-*.json"))
    contents = path.read_text(encoding="utf-8")
    assert str(store.root) not in contents
    assert json.loads(contents)["system_root"].startswith("sha256:")

    # Simulate a later process with no such environment secrets.
    monkeypatch.delenv("JAZN_TPA_TEST_TOKEN")
    monkeypatch.delenv("JAZN_TPA_TEST_SECRET")
    recovered = PlanStore(RunStore(store.root)).load(plan["plan_id"])
    assert recovered["source_request"]["kind"] == "master"
    assert recovered["tasks"][0]["id"] == "regression:smoke-isolation"
    assert recovered["tasks"][0]["status"] == "QUEUED"


def test_checkpoint_redacts_freeform_reason_without_rewriting_task_graph(store, monkeypatch):
    marker = "synthetic-secret-marker-for-operator"
    monkeypatch.setenv("JAZN_TPA_TEST_TOKEN", marker)
    store.redactor = Redactor()
    plan = build_plan(("smoke-isolation",), {"kind": "master", "value": ""})
    plan["tasks"][0]["reason"] = "Operator saw " + marker
    plans = PlanStore(store)
    plans.save(plan)
    restored = plans.load(plan["plan_id"])
    assert marker not in restored["tasks"][0]["reason"]
    assert "[UKRYTO]" in restored["tasks"][0]["reason"]
    assert restored["tasks"][0]["depends_on"] == []


def test_checkpoint_root_binding_rejects_tampering_without_modification(store):
    plans = PlanStore(store)
    plan = build_plan(("smoke-isolation",), {"kind": "master", "value": ""})
    plans.save(plan)
    path = next(plans.folder(plan["plan_id"]).glob("checkpoint-*.json"))
    tampered = json.loads(path.read_text(encoding="utf-8"))
    tampered["system_root"] = "sha256:" + "0" * 64
    path.write_text(json.dumps(tampered), encoding="utf-8")
    before = path.read_bytes()
    with pytest.raises(ValueError, match="Uszkodzony checkpoint planu"):
        plans.load(plan["plan_id"])
    assert path.read_bytes() == before


def test_checkpoint_reads_legacy_unredacted_root_binding(store):
    plans = PlanStore(store)
    plan = build_plan(("smoke-isolation",), {"kind": "master", "value": ""})
    plans.save(plan)
    path = next(plans.folder(plan["plan_id"]).glob("checkpoint-*.json"))
    legacy = json.loads(path.read_text(encoding="utf-8"))
    legacy["system_root"] = str(store.root)
    path.write_text(json.dumps(legacy), encoding="utf-8")
    assert plans.load(plan["plan_id"])["source_request"]["kind"] == "master"
