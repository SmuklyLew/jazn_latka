from __future__ import annotations

from pathlib import Path
import shutil
import subprocess

import pytest

from latka_jazn.tools.memory_sqlite_test04 import (
    ProtocolRequest, Test04Error, build_parser, repository_preflight,
)


@pytest.fixture
def repository(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    def git(*args: str) -> str:
        return subprocess.check_output(["git", "-C", str(root), *args], text=True, stderr=subprocess.STDOUT).strip()
    git("init", "-b", "test/approved")
    git("-c", "user.name=Synthetic", "-c", "user.email=synthetic@example.invalid",
        "commit", "--allow-empty", "-m", "synthetic repository")
    return root


def test_missing_expectation_fails_before_git_or_writes(tmp_path: Path) -> None:
    with pytest.raises(Test04Error, match="explicit expected_branch or expected_ref"):
        repository_preflight(tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_explicit_branch_and_ref_are_both_required_to_match(repository: Path) -> None:
    head = subprocess.check_output(["git", "-C", str(repository), "rev-parse", "HEAD"], text=True).strip()
    report = repository_preflight(repository, expected_branch="test/approved", expected_ref=head)
    assert report["resolved_expected_ref"] == head
    assert report["restore_point"]["worktree_clean"] is True
    with pytest.raises(Test04Error, match="wrong branch"):
        repository_preflight(repository, expected_branch="test/wrong", expected_ref=head)
    with pytest.raises(Test04Error, match="failed"):
        repository_preflight(repository, expected_branch="test/approved", expected_ref="refs/heads/absent")


def test_ref_rejects_stale_commit_and_accepts_explicit_detached_head(repository: Path) -> None:
    def git(*args: str) -> str:
        return subprocess.check_output(["git", "-C", str(repository), *args], text=True, stderr=subprocess.STDOUT).strip()
    old = git("rev-parse", "HEAD")
    git("-c", "user.name=Synthetic", "-c", "user.email=synthetic@example.invalid", "commit", "--allow-empty", "-m", "second")
    with pytest.raises(Test04Error, match="wrong ref"):
        repository_preflight(repository, expected_ref=old)
    git("checkout", "--detach", old)
    report = repository_preflight(repository, expected_ref=old)
    assert report["branch"] == ""
    assert report["head"] == old
    with pytest.raises(Test04Error, match="wrong branch"):
        repository_preflight(repository, expected_branch="test/approved", expected_ref=old)


def test_explicit_ref_does_not_bypass_dirty_tree_gate(repository: Path) -> None:
    (repository / "tracked.txt").write_text("tracked", encoding="utf-8")
    subprocess.run(["git", "-C", str(repository), "add", "tracked.txt"], check=True)
    with pytest.raises(Test04Error, match="tracked worktree is dirty"):
        repository_preflight(repository, expected_ref="HEAD")
    assert repository_preflight(repository, expected_ref="HEAD", allow_dirty=True)["allow_dirty"]


@pytest.mark.parametrize("value", [" ", "--help", " test/approved"])
def test_invalid_expectation_is_rejected(repository: Path, value: str) -> None:
    with pytest.raises(Test04Error, match="invalid expected"):
        repository_preflight(repository, expected_ref=value)


def test_parser_and_request_preserve_explicit_expectations(tmp_path: Path) -> None:
    args = build_parser().parse_args(["--expected-branch", "test/approved", "--expected-ref", "abc123"])
    request = ProtocolRequest(tmp_path, tmp_path / "manifest.json", tmp_path / "target",
                              expected_branch=args.expected_branch, expected_ref=args.expected_ref).normalized()
    assert request.expected_branch == "test/approved"
    assert request.expected_ref == "abc123"


def test_powershell_missing_expectation_fails_before_creating_workspace(repository: Path) -> None:
    shell = shutil.which("pwsh") or shutil.which("powershell")
    if shell is None:
        pytest.skip("PowerShell unavailable on this host")
    script = Path(__file__).resolve().parents[1] / "tools/Invoke-JaznMemorySqliteTest04.ps1"
    result = subprocess.run([shell, "-NoProfile", "-NonInteractive", "-File", str(script),
                             "-Root", str(repository), "-WriteTemplates"],
                            capture_output=True, text=True, errors="replace", timeout=30)
    assert result.returncode != 0
    assert "ExpectedBranch" in result.stdout + result.stderr
    assert not (repository / "workspace_runtime").exists()
