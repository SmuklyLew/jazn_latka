from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_generated_catalog_is_committed_before_metadata_and_single_push() -> None:
    workflow = _read(".github/workflows/stable-test-contracts.yml")

    catalog_commit = workflow.index('git commit -m "test: synchronize Test Studio contract catalog"')
    metadata_sync = workflow.index("latka_jazn.tools.release_metadata_sync")
    metadata_commit = workflow.index('git commit -m "release: synchronize canonical metadata')
    generated_push = workflow.index('git push origin "HEAD:')

    assert catalog_commit < metadata_sync < metadata_commit < generated_push
    assert workflow.count('git push origin "HEAD:') == 1
    assert "SOURCE_PROVENANCE.json" in workflow
    assert "PACKAGE_INTEGRITY_MANIFEST.json" in workflow
    assert "Verify canonical metadata is synchronized after generated catalog" in workflow


def test_branch_mutators_queue_instead_of_replacing_pending_runs() -> None:
    stable = _read(".github/workflows/stable-test-contracts.yml")
    release = _read(".github/workflows/release-hardening.yml")
    group = "jazn-branch-mutator-${{ github.event_name }}-${{ github.head_ref || github.ref_name }}"

    assert group in stable
    assert group in release
    assert "queue: max" in stable
    assert "queue: max" in release
    assert "cancel-in-progress: false" in stable
    assert "cancel-in-progress: false" in release


def test_pr_validation_materializes_catalog_without_mutating_branch() -> None:
    workflow = _read(".github/workflows/stable-test-contracts.yml")

    materialize = workflow.index("Materialize deterministic Test Studio catalog for PR validation")
    check = workflow.index("Verify deterministic Test Studio catalog")
    assert materialize < check
    assert "if: github.event_name == 'pull_request'" in workflow[materialize:check]
    assert "sync_contract_catalog.py --write" in workflow[materialize:check]
