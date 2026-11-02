"""Per-phase persistence must use the manifest frozen before test execution."""
import json
from types import SimpleNamespace

from tools.jazn_run_studio import test_evidence_plugin as plugin


def test_phase_reporting_does_not_requery_the_environment(tmp_path, monkeypatch):
    root = tmp_path / "SYSTEM"
    (root / "latka_jazn").mkdir(parents=True)
    (root / "latka_jazn/version.py").write_text('PACKAGE_VERSION="1.2.3"\n', encoding="utf-8")
    recorder = plugin.EvidenceRecorder(SimpleNamespace(rootpath=root), tmp_path / "evidence")
    monkeypatch.setattr(recorder, "_inventory", lambda: {})
    nodeid = "tests/synthetic.py::test_frozen_identity"
    recorder._create([SimpleNamespace(nodeid=nodeid)])
    assert recorder.report is not None
    folder = recorder.store.folder(recorder.report["run_id"])
    manifest = (folder / "manifest.json").read_bytes()
    def forbidden(*args, **kwargs):
        raise AssertionError("Phase reporting must not rebuild inventory or observe platform")
    with monkeypatch.context() as patch:
        patch.setattr(plugin, "_definition", forbidden)
        patch.setattr(plugin.platform, "system", forbidden)
        for phase in ("setup", "call", "teardown"):
            recorder.pytest_runtest_logreport(SimpleNamespace(
                nodeid=nodeid, when=phase, duration=0.001, failed=False,
                skipped=False, outcome="passed"))
    receipts = [json.loads(path.read_bytes())["event"] for path in folder.glob("pytest-*.json")]
    assert len(receipts) == 3
    assert {event["phase"] for event in receipts} == {"setup", "call", "teardown"}
    assert all(event["run_id"] == recorder.report["run_id"] for event in receipts)
    assert all(event["result"]["full_gate"] == "NOT_RUN" for event in receipts)
    assert (folder / "manifest.json").read_bytes() == manifest
