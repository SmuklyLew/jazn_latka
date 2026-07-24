from __future__ import annotations

import hashlib
import json
from pathlib import Path

from latka_jazn.tools.current_line_archive_audit import ARCHIVE_ROOT, run_audit
from latka_jazn.version import PACKAGE_VERSION

ROOT = Path(__file__).resolve().parents[1]


def test_current_active_tree_has_no_old_package_version_references() -> None:
    report = run_audit(ROOT)
    assert report.package_version == PACKAGE_VERSION == "v15.1.0.3.89"
    assert report.active_old_references == []
    assert report.archive_issues == []
    assert report.ok is True


def test_archive_preserves_exact_files_and_private_source_metadata_only() -> None:
    manifest = json.loads((ROOT / ARCHIVE_ROOT / "ARCHIVE_MANIFEST.json").read_text(encoding="utf-8"))
    private = [entry for entry in manifest["files"] if entry["retention"] == "metadata_only_private_source"]
    assert len(private) == 1
    assert private[0]["original_path"] == "latka_jazn/contracts/embedded_sources.py"
    assert private[0]["archive_path"] is None
    assert not (ROOT / "latka_jazn/contracts/embedded_sources.py").exists()

    for entry in manifest["files"]:
        if entry["retention"] != "exact_copy":
            continue
        archived = ROOT / entry["archive_path"]
        data = archived.read_bytes()
        assert len(data) == entry["size_bytes"]
        assert hashlib.sha256(data).hexdigest() == entry["sha256"]
