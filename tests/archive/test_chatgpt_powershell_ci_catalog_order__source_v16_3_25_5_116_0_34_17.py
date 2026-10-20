from __future__ import annotations

"""Prevent the catalog-sync race on PowerShell pull-request builds."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_powershell_pr_materializes_then_checks_catalog_before_release_metadata() -> None:
    workflow = (ROOT / ".github/workflows/powershell-terminal-regressions.yml").read_text(encoding="utf-8")
    create = "python -X utf8 tools/jazn_tests_studio/sync_contract_catalog.py --write"
    check = "python -X utf8 tools/jazn_tests_studio/sync_contract_catalog.py --check"
    release = "python -X utf8 -m latka_jazn.tools.release_metadata_sync"
    assert workflow.count(create) == 1
    assert workflow.count(check) == 1
    assert workflow.index(create) < workflow.index(check) < workflow.index(release)
    assert workflow.index(check) < workflow.index("Compile active Python")
    assert "git checkout -- SOURCE_PROVENANCE.json PACKAGE_INTEGRITY_MANIFEST.json tools/jazn_tests_studio/test_contracts.json" in workflow
    assert "Never push generated files from this PR job." in workflow
