from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
UPLOAD_ARTIFACT_V701_SHA = "043fb46d1a93c77aae656e7c1c64a875d1fc6a0a"


def _read(name: str) -> str:
    return (WORKFLOWS / name).read_text(encoding="utf-8")


def test_duplicate_and_one_shot_release_workflows_are_removed() -> None:
    assert not (WORKFLOWS / "release-metadata-sync.yml").exists()
    assert not (WORKFLOWS / "apply-master-release-metadata-auto-sync.yml").exists()
    assert not (ROOT / "tools" / "apply_master_release_metadata_auto_sync.py").exists()


def test_release_workflow_uses_one_dynamic_metadata_writer() -> None:
    text = _read("release-hardening.yml")
    previous_release = "v" + ".".join(("15", "1", "0", "3", "89"))
    assert previous_release not in text
    assert "master|update/*|tools/upgrade-*|hotfix/*|upgrade/*|fix/*" in text
    assert "PACKAGE_VERSION_FULL" in text
    assert "permissions:\n  contents: read" in text
    assert "permissions:\n      contents: write" in text
    assert "[skip ci]" in text


def test_release_workflow_concurrency_is_scoped_to_the_workflow() -> None:
    text = _read("release-hardening.yml")
    expected_group = (
        "group: ${{ github.workflow }}-${{ github.event_name }}-"
        "${{ github.head_ref || github.ref_name }}"
    )
    assert expected_group in text
    assert "cancel-in-progress: ${{ github.event_name == 'pull_request' }}" in text


def test_release_workflow_keeps_windows_atomicity_targeted_without_duplication() -> None:
    text = _read("release-hardening.yml")
    assert text.count('-m "not live_model and not live_mcp"') == 1
    assert "Targeted Windows runtime and path tests" in text
    assert "Turn atomicity and timeout regressions" in text
    assert "Security path and archive resource regressions" not in text
    assert "Full session integrity regressions" not in text
    assert "Active contract legacy guard" not in text

    general = text.split("- name: Targeted Windows runtime and path tests", 1)[1].split(
        "- name: Upload Windows pytest report on failure", 1
    )[0]
    atomicity = text.split("- name: Turn atomicity and timeout regressions", 1)[1].split(
        "- name: Upload Windows turn atomicity report on failure", 1
    )[0]
    for path in (
        "tests/test_turn_atomicity.py",
        "tests/test_turn_timeout_audit_nonblocking.py",
        "tests/test_runtime_stability_daemon_status.py",
    ):
        assert path not in general
        assert atomicity.count(path) == 1


def test_release_package_smoke_runs_once_and_only_after_pr_validation() -> None:
    text = _read("release-hardening.yml")
    assert "package-smoke --profile system" not in text
    assert text.count("package-smoke --profile release --json") == 1
    assert "if: github.event_name != 'pull_request'" in text
    assert "needs: [manifest_sync, verify_ubuntu, verify_windows]" in text


def test_upload_artifact_is_pinned_and_failure_only() -> None:
    text = _read("release-hardening.yml")
    refs = re.findall(r"uses:\s*actions/upload-artifact@([^\s#]+)", text)
    assert refs == [UPLOAD_ARTIFACT_V701_SHA] * 4
    assert all(re.fullmatch(r"[0-9a-f]{40}", ref) for ref in refs)
    assert text.count("if: failure()") == 4
    assert text.count("retention-days: 3") == 4


def test_cursor_conpty_workflow_is_pr_scoped_and_manually_runnable() -> None:
    text = _read("cursor-windows-conpty.yml")
    assert "workflow_dispatch:" in text
    assert "tools/memory-import-to-db" not in text
    assert "pull_request:" in text
    assert '"tools/windows_cursor_conpty_smoke.py"' in text
    assert "group: ${{ github.workflow }}-${{ github.ref }}" in text
