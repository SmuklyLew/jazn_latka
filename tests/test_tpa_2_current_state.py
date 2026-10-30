"""TPA 2.0 persistence contracts; all evidence is synthetic and run-owned."""
from copy import deepcopy
import json

import pytest

from tools.jazn_run_studio.tpa_current_state import current_state
from tools.jazn_run_studio.tpa_guidance import record_observation
from tools.jazn_run_studio.tpa_reports import RunStore, safe_child


@pytest.fixture
def store(tmp_path, monkeypatch):
    root = tmp_path / "SYSTEM"
    (root / "latka_jazn").mkdir(parents=True)
    (root / "latka_jazn/version.py").write_text('PACKAGE_VERSION="1.2.3"\n', encoding="utf-8")
    monkeypatch.setenv("JAZN_OPERATOR_STATE_ROOT", str(tmp_path / "operator"))
    return RunStore(root)


def completed(store, case="config-persistence", *, status="PASS", execution="regression", sha="a" * 40):
    report = store.create((case,), "test-python", {"memory_mode": "off"})
    report["source"].update(git_sha=sha, git_dirty=False)
    report["execution"] = execution
    row = report["results"][0]
    row.update(status=status, exit_code=0, reason="synthetic result")
    report["finished_utc"] = report["started_utc"]
    if status == "PASS":
        if execution == "regression":
            name = case + ".xml"
            safe_child(store.folder(report["run_id"]), name).write_text(
                '<testsuites><testsuite><testcase name="synthetic"/></testsuite></testsuites>', encoding="utf-8")
            row["junit"] = name
        else:
            name = case + ".live.json"
            safe_child(store.folder(report["run_id"]), name).write_text(
                json.dumps({"result": {"status": "PASS"}, "cleanup": {"ok": True}}), encoding="utf-8")
        report["artifacts"].append(name)
    store.save(report)
    return report


def test_projection_keeps_previous_case_across_new_run_and_restart(store):
    first = completed(store)
    completed(store, "smoke-isolation")
    # Persist explicit NOT_RUN: it is absence of an attempt, not a new failure.
    empty = store.create(("config-persistence",), "python", {})
    empty["results"][0]["status"] = "NOT_RUN"
    store.save(empty)
    state = current_state(RunStore(store.root), first["source"])
    assert len(state) == 22
    assert state["smoke-isolation"]["regression"]["status"] == "PASS"
    assert state["config-persistence"]["regression"]["status"] == "PASS"
    assert state["config-persistence"]["last_success"]["run_id"] == first["run_id"]
    assert state["config-persistence"]["full"] is None


def test_not_run_does_not_hide_pass(store):
    first = completed(store)
    empty = store.create(("config-persistence",), "python", {})
    empty["results"][0]["status"] = "NOT_RUN"
    store.save(empty)
    state = current_state(store, first["source"])["config-persistence"]
    assert state["regression"]["run_id"] == first["run_id"]
    assert state["regression"]["status"] == "PASS"


def test_channels_staleness_and_latest_failure_are_independent(store):
    regression = completed(store)
    live = completed(store, execution="live", sha="b" * 40)
    failed = completed(store, status="FAIL")
    state = current_state(store, failed["source"])["config-persistence"]
    assert state["regression"]["run_id"] == failed["run_id"]
    assert state["regression"]["status"] == "FAIL"
    assert state["live"]["run_id"] == live["run_id"]
    assert state["live"]["source_relation"] == "stale"
    assert state["last_success"]["run_id"] == live["run_id"]
    assert store.load(regression["run_id"])["results"][0]["status"] == "PASS"


@pytest.mark.parametrize("damage", ["missing", "invalid", "empty", "skipped"])
def test_damaged_junit_blocks_projection_without_rewriting_claim(store, damage):
    report = completed(store)
    row = report["results"][0]
    path = safe_child(store.folder(report["run_id"]), row["junit"])
    if damage == "missing":
        path.unlink()
    else:
        path.write_text({"invalid": "<broken", "empty": "", "skipped": '<testcase><skipped/></testcase>'}[damage], encoding="utf-8")
    state = current_state(store, report["source"])["config-persistence"]
    assert state["regression"]["status"] == "BLOCKED"
    assert state["regression"]["row"]["status"] == "PASS"
    assert state["last_success"] is None
    assert store.load(report["run_id"])["results"][0]["status"] == "PASS"


def test_full_acceptance_hashes_are_rechecked_after_restart(store):
    report = completed(store)
    row = report["results"][0]
    record_observation(store, report, "config-persistence", [0, 1, 2, 3], "Synthetic human observation", [row["junit"]], "PASS")
    state = current_state(RunStore(store.root), report["source"])["config-persistence"]
    assert state["full"]["status"] == "PASS"
    # Still parseable valid JUnit, but not the material the operator accepted.
    safe_child(store.folder(report["run_id"]), row["junit"]).write_text('<testcase name="changed"/>', encoding="utf-8")
    state = current_state(RunStore(store.root), report["source"])["config-persistence"]
    assert state["regression"]["status"] == "PASS"
    assert state["full"]["status"] == "BLOCKED"
    assert state["last_full_success"] is None


def test_revision_history_is_immutable_and_explicit_recovery_preserves_corruption(store):
    report = completed(store)
    originals = {p.name: p.read_bytes() for p in store.folder(report["run_id"]).glob("revision-*.json")}
    report["results"][0].update(status="FAIL", reason="new result")
    store.save(report)
    assert all(safe_child(store.folder(report["run_id"]), name).read_bytes() == raw for name, raw in originals.items())
    folder = store.folder(report["run_id"])
    safe_child(folder, "report.json").write_bytes(b"{corrupt")
    assert store.history() == []
    assert store.history_errors
    restored = RunStore(store.root).recover_report(report["run_id"])
    assert restored["results"][0]["status"] == "FAIL"
    assert any(p.read_bytes() == b"{corrupt" for p in folder.glob("recovered-*-report.json"))
    assert store.load(report["run_id"])["results"][0]["status"] == "FAIL"


def test_crash_between_revision_and_report_is_recoverable(store, monkeypatch):
    from tools.jazn_run_studio import tpa_reports
    report = completed(store)
    old = safe_child(store.folder(report["run_id"]), "report.json").read_bytes()
    report["results"][0].update(status="RUNNING", reason="new operation")
    with monkeypatch.context() as patch:
        patch.setattr(tpa_reports.os, "replace", lambda *_: (_ for _ in ()).throw(OSError("synthetic crash")))
        with pytest.raises(OSError):
            store.save(report)
    assert safe_child(store.folder(report["run_id"]), "report.json").read_bytes() == old
    recovered = RunStore(store.root).recover_report(report["run_id"])
    assert recovered["results"][0]["status"] == "RUNNING"


def test_projection_does_not_mutate_loaded_history(store):
    report = completed(store)
    history = store.history()
    original = deepcopy(history)
    result = current_state(store, {**report["source"], "git_sha": None}, history)
    assert result["config-persistence"]["last_attempt"]["source_relation"] == "uncertain"
    assert history == original
