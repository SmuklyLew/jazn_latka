"""Immutable evidence, missing scenarios, corruption and read-only portability."""
from copy import deepcopy
import json
from pathlib import Path
import shutil
import zipfile

import pytest

from tools.jazn_run_studio.tpa_reports import RunStore
from tools.jazn_run_studio.test_evidence_archive import (
    export_snapshot, history, import_snapshot, read_snapshot,
)


@pytest.fixture
def archive_store(tmp_path, monkeypatch):
    root = tmp_path / "SYSTEM"
    (root / "latka_jazn").mkdir(parents=True)
    (root / "latka_jazn/version.py").write_text('PACKAGE_VERSION="1.2.3"\n', encoding="utf-8")
    monkeypatch.setenv("JAZN_OPERATOR_STATE_ROOT", str(tmp_path / "operator"))
    return RunStore(root)


def read(store, report):
    return read_snapshot(store.folder(report["run_id"]), report["evidence_snapshot"])


def test_manifest_precedes_execution_and_all_22_have_txt_json(archive_store):
    report = archive_store.create(("chat-resume",), "synthetic-python", {})
    snapshot = read(archive_store, report)
    folder = archive_store.folder(report["run_id"])
    assert json.loads((folder / "manifest.json").read_bytes()) == snapshot["manifest"]
    assert len(snapshot["results"]) == 22
    assert snapshot["summary"]["counts"] == {"NOT_RUN": 21, "QUEUED": 1}
    for row in snapshot["results"]:
        assert "results/" + row["scenario_id"] + ".json" in snapshot["files"]
        assert "scenarios/" + row["scenario_id"] + ".txt" in snapshot["files"]
        assert row["full_gate_status"] == "NOT_RUN"


@pytest.mark.parametrize("status", ["NOT_RUN", "BLOCKED", "SKIPPED", "INTERRUPTED", "CANCELLED", "ERROR", "RUNNING", "FAIL", "PASS"])
def test_status_never_promotes_to_release_acceptance(archive_store, status):
    report = archive_store.create(("chat-resume",), "python", {})
    report["results"][0]["status"] = status
    archive_store.save(report)
    snapshot = read(archive_store, report)
    selected = next(row for row in snapshot["results"] if row["scenario_id"] == "chat-resume")
    assert selected["execution_status"] == status
    assert selected["full_gate_status"] == "NOT_RUN"
    assert snapshot["summary"]["release_status"] == "RELEASE_NOT_ACCEPTED"


def test_revisions_preserve_old_source_and_results(archive_store):
    report = archive_store.create(("chat-resume",), "python", {})
    first = report["evidence_snapshot"]
    before = read(archive_store, report)
    report["source"].update(git_sha="a" * 40, git_dirty=False)
    report["results"][0].update(status="BLOCKED", reason="no model")
    archive_store.save(report)
    assert report["evidence_snapshot"] != first
    assert read_snapshot(archive_store.folder(report["run_id"]), first) == before
    assert read(archive_store, report)["summary"]["source"]["git_sha"] == "a" * 40


def test_missing_or_modified_evidence_is_not_a_verified_result(archive_store):
    report = archive_store.create(("chat-resume",), "python", {})
    folder = archive_store.folder(report["run_id"])
    target = folder / report["evidence_snapshot"] / "results/chat-resume.json"
    target.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="SHA256"):
        read(archive_store, report)
    found, errors = history(archive_store.base)
    assert not found and len(errors) == 1


def test_read_external_copy_never_mutates_source(archive_store, tmp_path):
    report = archive_store.create(("chat-resume",), "python", {})
    external = tmp_path / "external"
    shutil.copytree(archive_store.base, external)
    before = {str(p.relative_to(external)): p.read_bytes() for p in external.rglob("*") if p.is_file()}
    found, errors = history(external)
    assert len(found) == 1 and not errors
    assert before == {str(p.relative_to(external)): p.read_bytes() for p in external.rglob("*") if p.is_file()}
    assert found[0]["summary"]["source"]["version"] == "1.2.3"


def test_incomplete_snapshot_does_not_hide_committed_previous_revision(archive_store):
    report = archive_store.create(("chat-resume",), "python", {})
    folder = archive_store.folder(report["run_id"])
    (folder / ("snapshot-" + "0" * 32)).mkdir()
    (folder / ("snapshot-" + "1" * 32 + ".tmp")).write_text("partial", encoding="utf-8")
    found, errors = history(archive_store.base)
    assert not errors and found[0]["summary"]["snapshot"] == report["evidence_snapshot"]


def test_changed_required_catalogue_is_refused_before_new_save(archive_store):
    report = archive_store.create(("chat-resume",), "python", {})
    original = deepcopy(report)
    report["selected"] = []
    with pytest.raises(ValueError, match="katalog"):
        archive_store.save(report)
    assert read(archive_store, original)["manifest"]["selected"] == ["chat-resume"]


def test_manifest_edit_and_source_relabelling_are_refused(archive_store):
    report = archive_store.create(("chat-resume",), "python", {})
    report["source"].update(git_sha="a" * 40, git_dirty=False)
    report["results"][0]["status"] = "RUNNING"
    archive_store.save(report)
    report["source"]["git_sha"] = "b" * 40
    with pytest.raises(ValueError, match="Źródło"):
        archive_store.save(report)
    report["source"]["git_sha"] = "a" * 40
    path = archive_store.folder(report["run_id"]) / "manifest.json"
    data = json.loads(path.read_bytes())
    data["scenarios"].pop()
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="manifest"):
        archive_store.save(report)


def test_export_contains_only_verified_text_and_can_be_read_after_extraction(archive_store, tmp_path):
    report = archive_store.create(("chat-resume",), "python", {"access_token": "private-credential"})
    folder = archive_store.folder(report["run_id"])
    (folder / "owner.json").write_text('{"secret":"do-not-export"}', encoding="utf-8")
    target = tmp_path / "export.zip"
    export_snapshot(folder, report["evidence_snapshot"], target, archive_store.root)
    with zipfile.ZipFile(target) as archive:
        assert all("owner.json" not in name for name in archive.namelist())
        assert b"private-credential" not in b"".join(archive.read(name) for name in archive.namelist())
    destination = tmp_path / "imported"
    import_snapshot(target, destination, archive_store.root)
    loaded = read_snapshot(destination / report["run_id"], report["evidence_snapshot"])
    assert loaded == read(archive_store, report)
    with pytest.raises(FileExistsError):
        export_snapshot(folder, report["evidence_snapshot"], target, archive_store.root)


@pytest.mark.parametrize("name", ["../escape.txt", "run-bad/snapshot-bad.json", "/absolute", "C:/unsafe", "run-" + "a" * 32 + "/../escape.txt"])
def test_import_refuses_unsafe_paths_before_creating_destination(archive_store, tmp_path, name):
    path = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(name, "untrusted data")
    destination = tmp_path / "refused-import"
    with pytest.raises(ValueError):
        import_snapshot(path, destination, archive_store.root)
    assert not destination.exists()


def test_import_checks_hashes_before_creating_destination(archive_store, tmp_path):
    report = archive_store.create(("chat-resume",), "python", {})
    original = tmp_path / "original.zip"
    export_snapshot(archive_store.folder(report["run_id"]), report["evidence_snapshot"], original, archive_store.root)
    corrupt = tmp_path / "corrupt.zip"
    with zipfile.ZipFile(original) as archive, zipfile.ZipFile(corrupt, "w") as output:
        for name in archive.namelist():
            output.writestr(name, b"{}" if name.endswith("summary.json") else archive.read(name))
    destination = tmp_path / "refused-corrupt"
    with pytest.raises(ValueError, match="SHA256"):
        import_snapshot(corrupt, destination, archive_store.root)
    assert not destination.exists()


def test_explicit_external_writable_store_still_protects_system(archive_store, tmp_path):
    second = RunStore(archive_store.root, evidence_base=tmp_path / "owned-evidence")
    report = second.create(("chat-resume",), "python", {})
    assert read(second, report)["summary"]["run_id"] == report["run_id"]
    with pytest.raises(ValueError):
        RunStore(archive_store.root, evidence_base=archive_store.root / "unsafe")


def test_leaf_symlink_cannot_supply_external_evidence(archive_store, tmp_path):
    report = archive_store.create(("chat-resume",), "python", {})
    folder = archive_store.folder(report["run_id"])
    path = folder / report["evidence_snapshot"] / "summary.json"
    target = tmp_path / "foreign.json"
    target.write_bytes(path.read_bytes())
    try:
        link = tmp_path / "probe-link"
        link.symlink_to(target)
    except OSError:
        pytest.skip("Symlink creation requires OS capability")
    path.unlink()
    path.symlink_to(target)
    with pytest.raises(ValueError, match="Dowiązanie"):
        read(archive_store, report)
