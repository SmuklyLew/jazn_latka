"""Cold Windows snapshot metadata must not depend on WMI inventory queries."""
import json
import sys
from types import SimpleNamespace

from tools.jazn_run_studio import test_evidence_archive as archive
from tests.test_jss_evidence_archive import archive_store


def test_windows_snapshot_uses_native_version_without_platform_queries(archive_store, monkeypatch):
    native = SimpleNamespace(platform_version=(10, 0, 26100))
    fake_sys = SimpleNamespace(platform="win32", getwindowsversion=lambda: native,
                               version_info=sys.version_info)
    monkeypatch.setattr(archive, "sys", fake_sys, raising=False)
    def forbidden():
        raise AssertionError("Snapshot must not call potentially blocking WMI platform inventory")
    monkeypatch.setattr(archive.platform, "system", forbidden)
    monkeypatch.setattr(archive.platform, "platform", forbidden)
    report = archive_store.create(("gui-daemon",), "synthetic-python", {})
    saved = archive.read_snapshot(archive_store.folder(report["run_id"]), report["evidence_snapshot"])
    environment = json.loads(saved["files"]["environment.json"])
    assert environment["os"] == "Windows"
    assert environment["platform"] == "Windows-10.0.26100"
    assert environment["writer_python_version"] == list(sys.version_info[:3])
    assert environment["writer_pointer_bits"] in {32, 64}
    assert len(saved["results"]) == 22
    assert saved["summary"]["counts"] == {"QUEUED": 1, "NOT_RUN": 21}


def test_host_environment_metadata_survives_verified_round_trip(archive_store):
    report = archive_store.create(("gui-daemon",), "synthetic-python", {})
    saved = archive.read_snapshot(archive_store.folder(report["run_id"]), report["evidence_snapshot"])
    environment = json.loads(saved["files"]["environment.json"])
    assert environment["os"]
    assert environment["platform"]
    assert environment["writer_python_version"] == list(sys.version_info[:3])
    if sys.platform == "win32":
        assert environment["os"] == "Windows"
        assert environment["platform"] == "Windows-" + ".".join(map(str, sys.getwindowsversion().platform_version))
