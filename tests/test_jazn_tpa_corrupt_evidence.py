"""Malformed evidence produces an actionable refusal, not an unhandled parser error."""
import pytest
from tools.jazn_run_studio.core import Redactor
from tools.jazn_run_studio.tpa_reports import junit_result, safe_child
from tests.test_jazn_tpa_evidence import store


def test_invalid_junit_has_a_controlled_error(tmp_path):
    path = tmp_path / "broken.xml"
    path.write_text("<testsuites><", encoding="utf-8")
    with pytest.raises(ValueError, match="Niepoprawny XML"):
        junit_result(path, 0, Redactor({}))


def test_export_refuses_corrupted_owned_xml_before_creating_zip(store, tmp_path):
    report = store.create(("smoke-isolation",), "test-python", {})
    safe_child(store.folder(report["run_id"]), "bad.xml").write_text("<broken", encoding="utf-8")
    report["artifacts"].append("bad.xml")
    target = tmp_path / "failed.zip"
    with pytest.raises(ValueError, match="Uszkodzony XML"):
        store.export_zip(report, target)
    assert not target.exists()
