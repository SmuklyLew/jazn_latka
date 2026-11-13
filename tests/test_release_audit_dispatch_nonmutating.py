"""Regression: manual audit-branch release validation must not mutate Git refs.

Keep automatic generated-artifact commits limited to the existing release
branch allowlist, while validating audit branches on the original SHA.
"""
from __future__ import annotations

from pathlib import Path


WORKFLOW = (
    Path(__file__).resolve().parents[1]
    / ".github"
    / "workflows"
    / "release-hardening.yml"
)


def _workflow() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_audit_dispatch_skips_both_mutating_generated_artifact_steps() -> None:
    text = _workflow()
    guard = (
        "if: github.event_name != 'pull_request' "
        "&& !startsWith(github.ref, 'refs/heads/integrate/') "
        "&& !startsWith(github.ref, 'refs/heads/audit/')"
    )
    assert text.count(guard) == 4
    assert "master|update/*|fix/*|hotfix/*|upgrade/*|release/*|tools/upgrade-*)" in text
    assert "master|update/*|fix/*|audit/*" not in text
    assert 'git push origin "HEAD:${target_branch}"' in text


def test_audit_dispatch_retains_metadata_and_catalog_validation() -> None:
    text = _workflow()
    guard = (
        "if: github.event_name == 'pull_request' "
        "|| startsWith(github.ref, 'refs/heads/integrate/') "
        "|| startsWith(github.ref, 'refs/heads/audit/')"
    )
    assert text.count(guard) == 5
    assert "Synchronize canonical release metadata after generated catalog" in text
    assert "Require committed audit-branch catalog and metadata" in text
    assert "sync_contract_catalog.py --check" in text
    assert "--root . --base-branch master --check --json" in text
    assert "Verify synchronization is idempotent" in text
    assert '[[ "$GITHUB_REF" == refs/heads/audit/* ]]' in text
    assert '-like "refs/heads/audit/*"' in text
    assert "needs: [manifest_sync, verify_ubuntu, verify_windows]" in text


def test_audit_is_not_added_to_automatic_push_branch_triggers() -> None:
    text = _workflow()
    header = text.split("pull_request:", 1)[0]
    assert '"audit/**"' not in header
    assert "workflow_dispatch:" in text
