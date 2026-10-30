"""Evidence semantics, isolation and honest scope, using synthetic records only."""
import json
from pathlib import Path
import zipfile
import xml.etree.ElementTree as ET
import pytest
from tools.jazn_run_studio.core import Redactor
from tools.jazn_run_studio.tpa_catalog import execution_map
from tools.jazn_run_studio.tpa_reports import RunStore, junit_result, safe_child
from tools.jazn_run_studio.tpa_guidance import record_observation
from tools.jazn_run_studio.tpa_reports import redact


@pytest.fixture
def store(tmp_path, monkeypatch):
    root = tmp_path / "SYSTEM"
    (root / "latka_jazn").mkdir(parents=True)
    (root / "latka_jazn/version.py").write_text('PACKAGE_VERSION="1.2.3"\n', encoding="utf-8")
    monkeypatch.setenv("JAZN_OPERATOR_STATE_ROOT", str(tmp_path / "operator"))
    return RunStore(root)


def test_each_of_22_cases_has_execution_resources_and_honest_limits():
    cases = execution_map()
    assert len(cases) == len({c["id"] for c in cases}) == 22
    assert all(c["files"] and c["requirements"] and len(c["guide"]) >= 4 for c in cases)
    assert all(c["coverage"] == "regression_subset" and c["full_gate"] == "NOT_RUN" for c in cases)


@pytest.mark.parametrize("body,code,status", [
    ('<testcase name="ok"/>', 0, "PASS"),
    ('<testcase name="skip"><skipped message="PySide6 missing"/></testcase>', 0, "SKIPPED"),
    ('<testcase name="ok"/><testcase name="skip"><skipped/></testcase>', 0, "SKIPPED"),
    ('<testcase name="bad"><failure message="assertion"/></testcase>', 1, "FAIL"),
    ('<testcase name="bad"><error message="import"/></testcase>', 2, "FAIL"),
    ('', 0, "SKIPPED"), ('<testcase name="ok"/>', 3, "FAIL"),
])
def test_junit_and_process_exit_must_both_support_result(tmp_path, body, code, status):
    path = tmp_path / "junit.xml"
    path.write_text('<testsuites><testsuite>' + body + '</testsuite></testsuites>', encoding="utf-8")
    result, xml = junit_result(path, code, Redactor({}))
    assert result["status"] == status
    ET.fromstring(xml)


def test_exit_zero_without_junit_is_not_pass(tmp_path):
    result, xml = junit_result(tmp_path / "absent.xml", 0, Redactor({}))
    assert result["status"] == "FAIL" and not xml


def test_reports_history_export_and_redaction_are_run_scoped(store, tmp_path):
    report = store.create(("config-persistence",), "test-python", {"memory_mode": "off"})
    report["results"][0].update(status="PASS", reason='secret="private-value"')
    report["finished_utc"] = "finished"
    name = "config-persistence.log"
    safe_child(store.folder(report["run_id"]), name).write_text("Bearer private-bearer\n", encoding="utf-8")
    report["artifacts"].append(name)
    store.save(report)
    second = store.create(("smoke-isolation",), "test-python", {})
    loaded = store.load(report["run_id"])
    assert loaded["summary"]["counts"] == {"PASS": 1}
    assert len(store.history()) == 2
    destination = tmp_path / "report.zip"
    store.export_zip(loaded, destination)
    with zipfile.ZipFile(destination) as archive:
        assert set(archive.namelist()) == {"report.json", "report.txt", name}
        text = " ".join(archive.read(n).decode() for n in archive.namelist())
        assert "private-value" not in text and "private-bearer" not in text
        assert second["run_id"] not in text
        assert json.loads(archive.read("report.json"))["run_id"] == report["run_id"]
    with pytest.raises(FileExistsError):
        store.export_zip(loaded, destination)
    with pytest.raises(ValueError):
        store.export_zip(loaded, store.root / "unsafe.zip")


def test_export_does_not_walk_runtime_or_allow_foreign_artifact(store, tmp_path):
    report = store.create(("gui-daemon",), "test-python", {})
    folder = store.folder(report["run_id"])
    (folder / "private.sqlite3").write_bytes(b"private")
    store.export_zip(report, tmp_path / "safe.zip")
    with zipfile.ZipFile(tmp_path / "safe.zip") as archive:
        assert "private.sqlite3" not in archive.namelist()
    report["artifacts"] = ["../foreign.log"]
    with pytest.raises(ValueError):
        store.export_zip(report, tmp_path / "bad.zip")


def test_interrupted_run_never_turns_pass_after_application_disappears(store, monkeypatch):
    from tools.jazn_run_studio import tpa_reports
    report = store.create(("gui-daemon", "config-persistence"), "test-python", {})
    report["results"][0]["status"] = "RUNNING"
    store.save(report)
    monkeypatch.setattr(tpa_reports, "process_alive", lambda pid: False)
    store.recover_interrupted()
    loaded = store.load(report["run_id"])
    assert {r["status"] for r in loaded["results"]} == {"INTERRUPTED"}
    assert loaded["finished_utc"]


def test_subcheck_does_not_authorize_real_turn_or_12_studio_acceptance(store):
    report = store.create(("ollama-two-turns", "studios-parity"), "test-python", {})
    report["finished_utc"] = "finished"
    for row in report["results"]:
        row["status"] = "PASS"
    proof = "example.txt"
    safe_child(store.folder(report["run_id"]), proof).write_text("synthetic evidence", encoding="utf-8")
    report["artifacts"].append(proof)
    for key, message in (("ollama-two-turns", "rzeczywistych"), ("studios-parity", "12 odrębnych")):
        with pytest.raises(ValueError, match=message):
            record_observation(store, report, key, [0, 1, 2, 3], "All steps observed", [proof], "PASS")


def test_human_observation_keeps_regression_result_and_append_only_evidence(store):
    report = store.create(("config-persistence",), "test-python", {})
    report["finished_utc"] = "finished"
    row = report["results"][0]
    row["status"] = "PASS"
    proof = "example.txt"
    safe_child(store.folder(report["run_id"]), proof).write_text("Observed save/reopen and CAS refusal", encoding="utf-8")
    report["artifacts"].append(proof)
    record_observation(store, report, "config-persistence", [0, 1, 2, 3], "Saved and reopened synthetic config", [proof], "PASS")
    record_observation(store, report, "config-persistence", [0], "Need another manual comparison", [proof], "BLOCKED")
    assert len(report["observations"]) == 2
    assert row["status"] == "PASS" and row["full_gate"] == "BLOCKED"
    assert len(list(store.folder(report["run_id"]).glob("observation-*.json"))) == 2


def test_version_change_preserves_history_and_refuses_transferred_acceptance(store):
    report = store.create(("config-persistence",), "test-python", {})
    report["finished_utc"] = "finished"
    store.save(report)
    (store.root / "latka_jazn/version.py").write_text('PACKAGE_VERSION="1.2.4"\n', encoding="utf-8")
    with pytest.raises(ValueError, match="bieżącej wersji"):
        record_observation(store, report, "config-persistence", [], "Historical", [], "BLOCKED")
    assert store.history()[0]["source"]["version"] == "1.2.3"


def test_structured_secret_values_are_redacted_without_corrupting_json(store):
    value = {"environment": {"access_token": "private value", "api_key": "private key", "password": "private password"}, "request_id": "synthetic-request"}
    clean = redact(value, Redactor({}))
    assert set(clean["environment"].values()) == {"[UKRYTO]"}
    assert clean["request_id"] == "synthetic-request"


def test_damaged_history_is_visible_and_does_not_hide_other_runs(store):
    valid = store.create(("config-persistence",), "test-python", {})
    broken = store.create(("smoke-isolation",), "test-python", {})
    safe_child(store.folder(broken["run_id"]), "report.json").write_text("{broken", encoding="utf-8")
    history = store.history()
    assert [r["run_id"] for r in history] == [valid["run_id"]]
    assert broken["run_id"] in store.history_errors[0]


def test_gui_and_exe_acceptance_requires_human_evidence_not_just_junit(store):
    report = store.create(("offline-exe", "ui-accessibility", "studio-memory"), "test-python", {})
    report["finished_utc"] = "finished"
    proof = "test.xml"
    safe_child(store.folder(report["run_id"]), proof).write_text("<testsuites/>", encoding="utf-8")
    report["artifacts"].append(proof)
    for row in report["results"]:
        row["status"] = "PASS"
        with pytest.raises(ValueError):
            record_observation(store, report, row["case_id"], [0, 1, 2, 3], "Only unit tests observed", [proof], "PASS")


def test_live_service_refusal_is_blocked_before_creating_runtime(store, tmp_path, monkeypatch):
    from tools.jazn_run_studio import tpa_live
    folder = tmp_path / "live"
    folder.mkdir()
    def unavailable(model):
        raise ConnectionRefusedError("synthetic private endpoint")
    monkeypatch.setattr(tpa_live, "ollama", unavailable)
    result = tpa_live.exercise(store.root, folder, "ollama-two-turns", "python", "synthetic-model")
    assert result["status"] == "BLOCKED"
    assert result["evidence"]["service_reachable"] is False
    assert not any(folder.iterdir())
    assert "private endpoint" not in result["reason"]


def test_cleanup_refuses_foreign_root_before_any_canonical_command(store, tmp_path):
    from tools.jazn_run_studio.tpa_live import cleanup
    folder = tmp_path / "owned"
    folder.mkdir()
    (folder / "owner.json").write_text(json.dumps({"root": str(store.root), "url": "http://127.0.0.1:1", "instance_id": None}), encoding="utf-8")
    with pytest.raises(ValueError, match="Niezgodny katalog"):
        cleanup(folder, "python")
