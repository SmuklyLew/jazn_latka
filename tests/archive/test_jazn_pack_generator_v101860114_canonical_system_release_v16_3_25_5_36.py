from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

import pytest

from tools import jazn_pack_generator as generator
from tools.jazn_pack_generator_app import staging
from tools.jazn_pack_generator_app.errors import PackSafetyError
from tools.jazn_pack_generator_app.models import ContentMode, PackPlan, PackRequest, SourceEntry

ROOT = Path(__file__).resolve().parents[1]


def test_canonical_system_staging_uses_release_inventory_not_working_tree(monkeypatch, tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    working = source_root / "drift.py"
    working.write_bytes(b"print('working tree')\r\n")
    request = PackRequest(source_root=source_root, output_root=tmp_path / "out", content=ContentMode.SYSTEM)
    original_plan = PackPlan(
        request=request,
        package_version="1.0-test",
        package_basename="jazn_latka_v1.0-test.system.zip",
        entries=(SourceEntry(source=working, archive_path="drift.py", size_bytes=working.stat().st_size),),
        excluded=(),
        source_total_size_bytes=working.stat().st_size,
    )
    canonical = b"print('git blob')\n"

    def fake_release(_root: Path, destination: Path) -> dict[str, object]:
        destination.mkdir(parents=True, exist_ok=True)
        (destination / "drift.py").write_bytes(canonical)
        manifest = {
            "files": [{"path": "drift.py", "size_bytes": len(canonical), "sha256": hashlib.sha256(canonical).hexdigest()}],
            "excluded_files": [],
        }
        (destination / "PACKAGE_INTEGRITY_MANIFEST.json").write_text(json.dumps(manifest), encoding="utf-8")
        return {"ok": True, "source_commit": "abc", "source_tree": "def", "status": "verified_export_without_git_history"}

    monkeypatch.setattr(staging, "_run_release_staging", fake_release)
    result = staging.materialize_canonical_staging(original_plan, tmp_path / "staging")
    row = next(item for item in result.plan.entries if item.archive_path == "drift.py")
    assert row.source.read_bytes() == canonical
    assert row.source.read_bytes() != working.read_bytes()
    assert result.member_sha256["drift.py"] == hashlib.sha256(canonical).hexdigest()
    metadata = result.verification_metadata()
    assert metadata["staging_mode"] == "canonical-release-staging"
    assert metadata["canonical_release_bytes"] is True
    assert metadata["byte_exact_source_copy"] is False
    assert metadata["eol_policy"] == "canonical_git_blobs_fail_closed"


def test_duplicate_zip_member_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "duplicate.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("run.py", b"one")
        archive.writestr("run.py", b"two")
    with pytest.raises(PackSafetyError, match="Duplikat"):
        generator.verify_package(path)


@pytest.mark.integration
def test_system_package_uses_canonical_release_and_extract_reverify(tmp_path: Path) -> None:
    result = generator.run_pack_request(
        source=ROOT,
        out_dir=tmp_path / "packages",
        content="system",
        compression_level=0,
    )
    manifest = json.loads(Path(result["manifest_path"]).read_text(encoding="utf-8"))
    verification = manifest["verification"]
    assert manifest["generator_version"] == "10.1.86.0.114"
    assert manifest["source"]["source_basis"] == "canonical_release"
    assert manifest["source"]["staging_mode"] == "canonical-release-staging"
    assert verification["eol_policy"] == "canonical_git_blobs_fail_closed"
    assert verification["system_extract_reverify"]["ok"] is True
    assert verification["system_extract_reverify"]["package_integrity"]["ok"] is True
    assert verification["system_extract_reverify"]["source_provenance"]["status"] == "verified_export_without_git_history"

    archive_path = Path(result["logical_archive"])
    committed_run = subprocess.run(
        ["git", "-C", str(ROOT), "show", "HEAD:run.py"],
        check=True,
        capture_output=True,
    ).stdout
    with zipfile.ZipFile(archive_path, "r") as archive:
        assert archive.read("run.py") == committed_run
        assert "PACKAGE_INTEGRITY_MANIFEST.json" in archive.namelist()
        assert archive.testzip() is None
