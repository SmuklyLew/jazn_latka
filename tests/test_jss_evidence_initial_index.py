"""The first durable index must remain readable before any pytest phase."""
import sys
from types import SimpleNamespace

import pytest

from tools.jazn_run_studio.test_evidence_plugin import EvidenceRecorder
from tools.jazn_run_studio import tpa_reports


def source_root(tmp_path):
    root = tmp_path / "SYSTEM"
    (root / "latka_jazn").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "latka_jazn/version.py").write_text('PACKAGE_VERSION="1.2.3"\n', encoding="utf-8")
    (root / "pyproject.toml").write_text('[tool.pytest.ini_options]\ntestpaths=["tests"]\n', encoding="utf-8")
    (root / "tests/test_probe.py").write_text('def test_probe(): assert True\n', encoding="utf-8")
    return root


def test_pytest_initial_index_uses_registered_limit_before_any_test_phase(tmp_path, monkeypatch):
    root = source_root(tmp_path)
    recorder = EvidenceRecorder(SimpleNamespace(rootpath=root), tmp_path / "reports")
    recorder._create([SimpleNamespace(nodeid="tests/test_probe.py::test_probe")])
    report = recorder.report
    assert report is not None
    index = recorder.store.folder(report["run_id"]) / "report.json"
    # Lower the ordinary-report ceiling to exercise this boundary cheaply;
    # production ceilings are unchanged and registered evidence stays bounded.
    monkeypatch.setattr(tpa_reports, "MAX_REPORT", 1024)
    assert index.stat().st_size > tpa_reports.MAX_REPORT
    loaded = recorder.store.load(report["run_id"])
    assert loaded["execution"] == "pytest"
    assert all(row["status"] == "QUEUED" for row in loaded["results"])


def test_ordinary_tpa_index_does_not_receive_the_registered_pytest_limit(tmp_path, monkeypatch):
    root = source_root(tmp_path)
    store = tpa_reports.RunStore(root, evidence_base=tmp_path / "reports")
    report = store.create(("chat-resume",), sys.executable, {})
    monkeypatch.setattr(tpa_reports, "MAX_REPORT", 1024)
    assert (store.folder(report["run_id"]) / "report.json").stat().st_size > tpa_reports.MAX_REPORT
    with pytest.raises(ValueError, match="Raport TPA"):
        store.load(report["run_id"])
