from __future__ import annotations

import json
import pytest
import subprocess
from pathlib import Path

from latka_jazn.tools.current_line_v90_migration import (
    ARCHIVE_ROOT,
    scan_active_old_references,
)
from latka_jazn.version import PACKAGE_VERSION
from latka_jazn.version_contract import (
    LEGACY_CURRENT_LINE_VERSION,
    LEGACY_MEMORY_SOURCE_VERSION,
    V90_MIGRATION_TARGET_VERSION,
    component_schema_aliases,
    component_schema_version,
    mentions_current_jazn_version,
    mentions_jazn_version,
    normalize_component_schema,
)


def test_component_schema_is_release_independent_and_accepts_legacy_alias() -> None:
    assert component_schema_version("turn_trace") == "turn_trace/v1"
    assert normalize_component_schema(
        "turn_trace", f"turn_trace/{LEGACY_CURRENT_LINE_VERSION}"
    ) == "turn_trace/v1"
    assert component_schema_aliases("turn_trace")[0] == "turn_trace/v1"


def test_dynamic_version_detection_accepts_current_and_previous_release() -> None:
    assert mentions_jazn_version(f"zaktualizuj do {PACKAGE_VERSION}") is True
    assert mentions_current_jazn_version(f"status {PACKAGE_VERSION}") is True
    assert mentions_jazn_version(f"migracja z {LEGACY_CURRENT_LINE_VERSION}") is True
    assert mentions_jazn_version("zwykła rozmowa bez numeru") is False


def test_legacy_memory_source_version_remains_distinct_from_runtime_version() -> None:
    assert LEGACY_MEMORY_SOURCE_VERSION != PACKAGE_VERSION
    assert LEGACY_MEMORY_SOURCE_VERSION.startswith("v" + ".".join(("15", "0", "3")) + ".")


def test_current_tree_has_no_unapproved_old_references() -> None:
    root = Path(__file__).resolve().parents[1]
    findings, approved_legacy = scan_active_old_references(root)
    assert findings == []
    assert approved_legacy >= 0


def test_v90_scanner_does_not_treat_later_release_history_as_unfinished_migration(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)
    sample = repo / "later-release.md"
    sample.write_text("Historical report for v15.1.0.3.96\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "later-release.md"], check=True)
    findings, _ = scan_active_old_references(repo)
    assert findings == []


def test_v90_archive_manifest_preserves_exact_bytes() -> None:
    root = Path(__file__).resolve().parents[1]
    manifest_path = root / ARCHIVE_ROOT / "ARCHIVE_MANIFEST.json"
    if not manifest_path.exists():
        pytest.skip("developer archive is not included in the clean release tree")
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "current_line_archive/v1"
    assert payload["target_package_version"] == V90_MIGRATION_TARGET_VERSION
    for entry in payload["files"]:
        if entry["retention"] != "exact_copy":
            continue
        archived = root / entry["archive_path"]
        data = archived.read_bytes()
        assert len(data) == entry["size_bytes"]
        import hashlib
        assert hashlib.sha256(data).hexdigest() == entry["sha256"]


def test_git_diff_has_no_whitespace_errors() -> None:
    root = Path(__file__).resolve().parents[1]
    completed = subprocess.run(
        ["git", "-C", str(root), "diff", "--check"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
