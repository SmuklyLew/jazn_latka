"""Synthetic manual-write fault cases; no real operator acceptance is granted."""
from copy import deepcopy
import os

import pytest
from tools.jazn_run_studio import tpa_guidance as guidance
from tools.jazn_run_studio.tpa_reports import RunStore, utc


@pytest.fixture
def run(tmp_path):
    root = tmp_path / "SYSTEM"
    (root / "latka_jazn").mkdir(parents=True)
    (root / "latka_jazn/version.py").write_text('PACKAGE_VERSION="1.2.3"\n',encoding="utf-8")
    store = RunStore(root,evidence_base=tmp_path / "reports")
    report = store.create(("config-persistence",),"synthetic-python",{})
    report["finished_utc"] = utc()
    report["results"][0].update(status="BLOCKED",reason="Synthetic fixture; no workflow executed")
    store.save(report)
    source = tmp_path / "synthetic-proof.txt"
    source.write_text("Synthetic proof for persistence tests only\n",encoding="utf-8")
    return store,report,source


def perform(operation, store, report, source):
    if operation == "attachment":
        return guidance.attach_evidence(store,report,source)
    return guidance.record_observation(store,report,"config-persistence",[],
        "Synthetic failure observation; not operator acceptance",[],"FAIL")


@pytest.mark.parametrize("operation",["attachment","observation"])
@pytest.mark.parametrize("failure",["commit","fsync"])
def test_failed_manual_write_keeps_caller_and_disk_at_last_valid_revision(run,monkeypatch,operation,failure):
    store,report,source = run
    before = deepcopy(report)
    disk_before = store.load(report["run_id"])
    def fail(*_args,**_kwargs):
        raise OSError("Synthetic write failure")
    # Restore global fsync before pytest/evidence plugins persist the call
    # outcome. The injected fault belongs only to this owned operation.
    with monkeypatch.context() as fault:
        if failure == "commit":
            fault.setattr(store,"save",fail)
        else:
            fault.setattr(os,"fsync",fail)
        with pytest.raises(OSError,match="Synthetic write failure"):
            perform(operation,store,report,source)
    assert report == before
    assert store.load(report["run_id"]) == disk_before
    assert report["results"][0]["full_gate"] == "NOT_RUN"


@pytest.mark.parametrize("operation",["attachment","observation"])
def test_manual_artifact_is_synced_before_commit_and_adopted_afterwards(run,monkeypatch,operation):
    store,report,source = run
    result_rows, selected_row = report["results"], report["results"][0]
    original_save,original_sync = store.save,os.fsync
    synced = []
    def sync(fd):
        original_sync(fd)
        synced.append(fd)
    def save(candidate):
        assert synced, "Original artifact must be durable before report commit"
        assert candidate is not report
        assert report["artifacts"] == []
        original_save(candidate)
    monkeypatch.setattr(os,"fsync",sync)
    monkeypatch.setattr(store,"save",save)
    perform(operation,store,report,source)
    saved = store.load(report["run_id"])
    assert len(report["artifacts"]) == 1
    assert saved["artifacts"] == report["artifacts"]
    assert saved["results"] == report["results"]
    assert report["results"] is result_rows and report["results"][0] is selected_row
    assert selected_row == saved["results"][0]
    assert saved["results"][0]["status"] == "BLOCKED"
    assert saved["results"][0]["full_gate"] == ("FAIL" if operation == "observation" else "NOT_RUN")
