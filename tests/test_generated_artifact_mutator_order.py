from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_release_hardening_is_single_generated_artifact_branch_owner() -> None:
    stable = _read(".github/workflows/stable-test-contracts.yml")
    release = _read(".github/workflows/release-hardening.yml")

    assert "contents: write" not in stable
    assert "git push origin" not in stable
    assert "github-actions[bot]" not in stable

    catalog_sync = release.index("Synchronize active Test Studio catalog before release metadata")
    catalog_commit = release.index('git commit -m "test: synchronize Test Studio contract catalog"')
    metadata_sync = release.index("Synchronize canonical release metadata after generated catalog")
    metadata_commit = release.index('git commit -m "release: synchronize canonical metadata')
    generated_push = release.index('git push origin "HEAD:')

    assert catalog_sync < catalog_commit < metadata_sync < metadata_commit < generated_push
    assert release.count('git push origin "HEAD:') == 1
    assert "queue: max" in release
    assert "SOURCE_PROVENANCE.json" in release
    assert "PACKAGE_INTEGRITY_MANIFEST.json" in release


def test_validation_workflows_materialize_generated_catalog_without_branch_write() -> None:
    stable = _read(".github/workflows/stable-test-contracts.yml")
    release = _read(".github/workflows/release-hardening.yml")

    assert "Materialize deterministic Test Studio catalog for validation" in stable
    assert "sync_contract_catalog.py --write" in stable
    assert "Test governance against materialized catalog" in stable

    assert release.count("Materialize Test Studio catalog locally for PR validation") == 2
    assert release.count("tools/jazn_tests_studio/test_contracts.json") >= 3
    assert "git checkout -- \\" in release


def test_generated_push_is_guarded_to_non_pr_branch_mutation() -> None:
    release = _read(".github/workflows/release-hardening.yml")

    marker = "Commit release metadata and push the generated sequence once"
    start = release.index(marker)
    block = release[start : start + 2600]
    assert "if: github.event_name != 'pull_request'" in block
    assert "JAZN_HEAD_REPOSITORY" in block
    assert "target_branch" in block
    assert "git fetch origin" in block
