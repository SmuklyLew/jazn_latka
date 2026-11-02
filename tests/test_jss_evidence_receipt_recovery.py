"""Actual abrupt pytest exit leaves bounded, read-only, fail-closed history."""
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from uuid import uuid4
import zipfile

import pytest

from tools.jazn_run_studio.test_evidence_archive import _json, history
from tools.jazn_run_studio.test_evidence_plugin import _definition
from tools.jazn_run_studio.tpa_reports import RunStore
from tools.jazn_run_studio import test_evidence_archive as archive


@pytest.fixture(scope="module")
def crashed_source(tmp_path_factory):
    tmp_path = tmp_path_factory.mktemp("abrupt-pytest")
    root = tmp_path / "SYSTEM"
    (root / "tests").mkdir(parents=True)
    (root / "latka_jazn").mkdir()
    (root / "latka_jazn/version.py").write_text('PACKAGE_VERSION="1.2.3"\n', encoding="utf-8")
    (root / "pyproject.toml").write_text('[tool.pytest.ini_options]\ntestpaths=["tests"]\n', encoding="utf-8")
    (root / "tests/test_cases.py").write_text(
        'import os\ndef test_done(): assert 2 + 2 == 4\ndef test_crash(): os._exit(7)\n', encoding="utf-8")
    base = tmp_path / "reports"
    env = {key: value for key, value in os.environ.items()
           if not key.upper().startswith(("JAZN_", "PYTEST_", "PYTHONPATH"))}
    env.update(PYTHONPATH=str(Path(__file__).resolve().parents[1]), PYTEST_DISABLE_PLUGIN_AUTOLOAD="1",
               PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="1", JAZN_TEST_EVIDENCE_DIR=str(base))
    child = subprocess.run([sys.executable, "-X", "utf8", "-m", "pytest", "-q", "-p", "no:cacheprovider",
                            "-p", "tools.jazn_run_studio.test_evidence_plugin"],
                           cwd=root, env=env, capture_output=True, timeout=60, check=False)
    assert child.returncode == 7, child.stdout + child.stderr
    folder, = base.glob("run-*")
    return base, folder, root


@pytest.fixture
def crashed_run(tmp_path, crashed_source):
    source, folder, root = crashed_source
    base = tmp_path / "reports"
    shutil.copytree(source, base)
    return base, base / folder.name, root


def _fingerprints(folder):
    return {str(path.relative_to(folder)): (path.stat().st_mtime_ns, sha256(path.read_bytes()).hexdigest())
            for path in folder.rglob("*") if path.is_file()}


def test_manifest_is_redacted_before_it_is_frozen(tmp_path, monkeypatch):
    secret = "synthetic-only-freeze-credential-9138"
    monkeypatch.setenv("JSS_SYNTHETIC_API_KEY", secret)
    root = tmp_path / "SYSTEM"
    (root / "latka_jazn").mkdir(parents=True)
    (root / "latka_jazn/version.py").write_text('PACKAGE_VERSION="1.2.3"\n', encoding="utf-8")
    case = _definition("tests/test_cases.py::test_value[" + secret + "]")
    store = RunStore(root, evidence_base=tmp_path / "reports")
    report = store.create((case["id"],), sys.executable, {}, catalogue=[case])
    folder = store.folder(report["run_id"])
    assert report["selected"] == [case["id"]]
    assert secret not in (folder / "manifest.json").read_text(encoding="utf-8")
    runs, errors = history(store.base)
    assert not errors and len(runs) == 1
    assert all(secret.encode() not in raw for raw in runs[0]["files"].values())


def test_legacy_manifest_and_redacted_receipts_match_without_rewriting_sources(tmp_path, monkeypatch):
    root = tmp_path / "SYSTEM"
    (root / "latka_jazn").mkdir(parents=True)
    (root / "latka_jazn/version.py").write_text('PACKAGE_VERSION="1.2.3"\n', encoding="utf-8")
    original_name = "tests/test_cases.py::test_value[token=synthetic-only-legacy]"
    case = _definition(original_name)
    initialize = archive.initialize
    manifest = archive.manifest

    def legacy_manifest(report):
        value = manifest(report)
        value.pop("redaction_policy")
        return value

    def legacy_freeze(folder, report):
        # Reproduce the old serialized format using a synthetic credential.
        # Runtime code must never write unredacted names again.
        report["coverage_map"][0]["title"] = original_name
        initialize(folder, report)

    monkeypatch.setattr(archive, "initialize", legacy_freeze)
    monkeypatch.setattr(archive, "manifest", legacy_manifest)
    store = RunStore(root, evidence_base=tmp_path / "reports")
    report = store.create((case["id"],), sys.executable, {}, catalogue=[case])
    folder = store.folder(report["run_id"])
    for index, (phase, status) in enumerate((("setup", "RUNNING"), ("call", "PASS"), ("teardown", "PASS"))):
        row = {**report["results"][0], "status": status, "reason": phase + ": passed",
               "started_utc": "2026-11-01T00:00:00+00:00", "duration_seconds": float(index)}
        if phase == "teardown":
            row["finished_utc"] = "2026-11-01T00:00:02+00:00"
        event = {"schema": "jazn_pytest_receipt/v1", "run_id": report["run_id"], "source": report["source"],
                 "phase": phase, "saved_utc": f"2026-11-01T00:00:0{index}+00:00", "result": row}
        receipt = folder / (case["id"] + "-" + uuid4().hex + ".json")
        _replace_receipt(receipt, event)
        receipt.with_suffix(".txt").write_bytes((original_name + "\n" + status + "\n" + row["reason"] + "\n").encode())
    before = _fingerprints(folder)
    runs, errors = history(store.base)
    assert not errors and len(runs) == 1
    assert runs[0]["results"][0]["execution_status"] == "PASS"
    assert "synthetic-only-legacy" not in runs[0]["results"][0]["name"]
    assert _fingerprints(folder) == before
    destination = tmp_path / "legacy-export.zip"
    with pytest.raises(ValueError, match="niezredagowane"):
        archive.export_snapshot(folder, report["evidence_snapshot"], destination, root)
    assert not destination.exists()


def _by_name(run):
    names = {item["scenario_id"]: item["name"].split("::")[-1] for item in run["manifest"]["scenarios"]}
    return {names[item["scenario_id"]]: item for item in run["results"]}


def _replace_receipt(path, event):
    path.write_bytes(_json({"sha256": sha256(_json(event)).hexdigest(), "event": event}))
    row = event["result"]
    path.with_suffix(".txt").write_bytes((row["title"] + "\n" + row["status"] + "\n" + row["reason"] + "\n").encode())


def _receipt(folder, phase, test_name="test_done"):
    for path in folder.glob("pytest-*.json"):
        event = json.loads(path.read_bytes())["event"]
        if event["phase"] == phase and event["result"]["title"].endswith("::" + test_name):
            return path, event
    raise AssertionError("Missing real phase receipt")


def test_actual_crash_recovers_completed_case_without_promoting_incomplete_call(crashed_run):
    base, folder, _ = crashed_run
    before = _fingerprints(folder)
    runs, errors = history(base)
    assert not errors and len(runs) == 1
    run = runs[0]
    outcomes = _by_name(run)
    assert outcomes["test_done"]["execution_status"] == "PASS"
    assert outcomes["test_crash"]["execution_status"] == "RUNNING"
    assert outcomes["test_crash"]["finished_utc"] is None
    assert all(item["full_gate_status"] == "NOT_RUN" for item in run["results"])
    assert run["summary"]["receipt_recovery"] == "UNSEALED"
    assert run["summary"]["release_status"] == "RELEASE_NOT_ACCEPTED"
    assert run["summary"]["finished_utc"] is None
    assert _fingerprints(folder) == before  # No repair, index or process operation.


def test_pass_call_without_teardown_is_not_pass(crashed_run):
    base, folder, _ = crashed_run
    path, _ = _receipt(folder, "teardown")
    path.unlink()
    path.with_suffix(".txt").unlink()
    runs, errors = history(base)
    assert not errors
    assert _by_name(runs[0])["test_done"]["execution_status"] == "RUNNING"


@pytest.mark.parametrize("corruption", ["hash", "source", "run", "case", "txt", "duplicate", "phase", "full-gate"])
def test_inconsistent_or_ambiguous_receipt_is_an_error_not_historical_pass(crashed_run, corruption):
    base, folder, _ = crashed_run
    path, event = _receipt(folder, "teardown")
    if corruption == "hash":
        envelope = json.loads(path.read_bytes())
        envelope["sha256"] = "0" * 64
        path.write_bytes(_json(envelope))
    elif corruption == "txt":
        path.with_suffix(".txt").write_text("PASS", encoding="utf-8")
    elif corruption == "duplicate":
        other = path.with_name(path.name[:-37] + "1" * 32 + ".json")
        other.write_bytes(path.read_bytes())
        other.with_suffix(".txt").write_bytes(path.with_suffix(".txt").read_bytes())
    else:
        if corruption == "source":
            event["source"]["version"] = "different"
        elif corruption == "run":
            event["run_id"] = "run-" + "0" * 32
        elif corruption == "case":
            event["result"]["case_id"] = "pytest-" + "0" * 32
        elif corruption == "phase":
            event["phase"] = "not-a-pytest-phase"
        elif corruption == "full-gate":
            event["result"]["full_gate"] = "PASS"
        _replace_receipt(path, event)
    runs, errors = history(base)
    assert not runs and len(errors) == 1
    assert folder.name in errors[0]


def test_qt_history_displays_unsealed_receipts_and_refuses_snapshot_export(crashed_run, monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication
    from tools.jazn_run_studio.test_history_view import TestHistoryPanel
    base, _, root = crashed_run
    app = QApplication.instance() or QApplication([])
    runs, errors = history(base)
    panel = TestHistoryPanel(root)
    panel.loaded({"runs": runs, "errors": errors, "sha": None, "dirty": None, "base": base})
    assert "NIEZAMKNIĘTY" in panel.summary.text()
    assert not panel.export_button.isEnabled()
    panel.export_selected()
    assert "raportu końcowego" in panel.errors.text()
    panel.status.setCurrentText("PASS")
    assert panel.table.rowCount() == 1
    assert "test_done" in panel.details.toPlainText()
    panel.close()
    panel.deleteLater()
    app.processEvents()


@pytest.mark.parametrize("kind", ["not-zip", "null-seal"])
def test_archive_worker_finishes_with_error_for_malformed_import(tmp_path, monkeypatch, kind):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication
    from tools.jazn_run_studio.test_history_view import _ArchiveJob
    app = QApplication.instance() or QApplication([])
    root = tmp_path / "SYSTEM"
    root.mkdir()
    source = tmp_path / "bad.zip"
    if kind == "not-zip":
        source.write_bytes(b"This is synthetic invalid input, not a ZIP")
    else:
        prefix = "run-" + "0" * 32 + "/snapshot-" + "1" * 32
        with zipfile.ZipFile(source, "w") as output:
            output.writestr(prefix + ".json", "null")
            output.writestr(prefix + "/integrity.json", "{}")
    before = source.read_bytes()
    destination = tmp_path / "import"
    results = []
    job = _ArchiveJob("import", (source, destination, root))
    job.signals.finished.connect(results.append)
    job.run()
    assert len(results) == 1 and "error" in results[0]
    assert results[0]["error"].startswith("BadZipFile" if kind == "not-zip" else "AttributeError")
    assert source.read_bytes() == before and not destination.exists()
    app.processEvents()
