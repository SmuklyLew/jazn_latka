"""Real local Git copies, immutable identities, and hostile ZIP refusals."""
from pathlib import Path
import subprocess
import zipfile

import pytest

from tools.jazn_run_studio.tpa_sources import _extract_zip, prepare_source


def command(root, *args):
    result = subprocess.run(["git", "-C", str(root), *args], capture_output=True, check=True)
    return result.stdout.decode("utf-8").strip()


@pytest.fixture
def repo(tmp_path, monkeypatch):
    monkeypatch.setenv("JAZN_OPERATOR_STATE_ROOT", str(tmp_path / "operator"))
    root = tmp_path / "repo"
    root.mkdir()
    command(root, "init", "-b", "master")
    command(root, "config", "user.email", "tpa@example.invalid")
    command(root, "config", "user.name", "TPA synthetic test")
    (root / "latka_jazn").mkdir()
    (root / "latka_jazn/version.py").write_text('PACKAGE_VERSION="1.2.3"\n', encoding="utf-8")
    (root / "run.py").write_text("# synthetic public starter\n", encoding="utf-8")
    (root / "main.py").write_text("# synthetic control plane\n", encoding="utf-8")
    (root / "tests").mkdir()
    (root / "tests/test_package_smoke_workspace_isolation.py").write_text("def test_source(): assert True\n", encoding="utf-8")
    command(root, "add", ".")
    command(root, "commit", "-m", "synthetic base")
    command(root, "remote", "add", "origin", str(root))
    return root


def test_default_master_fetch_materializes_detached_copy_without_changing_owner(repo, tmp_path):
    head = command(repo, "rev-parse", "HEAD")
    (repo / "uncommitted.txt").write_text("operator work", encoding="utf-8")
    before = command(repo, "status", "--porcelain")
    result = prepare_source(repo, tmp_path / "owned-master")
    selected = Path(result["root"])
    assert selected != repo
    assert result["source"]["git_sha"] == head
    assert result["source"]["integrity"] == "clean_detached_git_tree"
    assert command(selected, "rev-parse", "HEAD") == head
    assert command(selected, "branch", "--show-current") == ""
    assert command(repo, "branch", "--show-current") == "master"
    assert command(repo, "status", "--porcelain") == before
    assert not (selected / "uncommitted.txt").exists()


@pytest.mark.parametrize("kind,value,ref", [("branch", "candidate", "refs/heads/candidate"),
    ("pr", "17", "refs/pull/17/head"), ("merge", "17", "refs/pull/17/merge")])
def test_branch_pr_and_server_merge_ref_are_bound_to_exact_sha(repo, tmp_path, kind, value, ref):
    head = command(repo, "rev-parse", "HEAD")
    command(repo, "update-ref", ref, head)
    result = prepare_source(repo, tmp_path / ("owned-" + kind), kind=kind, value=value)
    assert result["source"]["git_sha"] == head
    assert result["source"]["source_kind"] == kind


def test_local_dirty_checkout_is_refused_and_destination_is_never_reused(repo, tmp_path):
    destination = tmp_path / "owned"
    prepare_source(repo, destination, kind="local")
    with pytest.raises(ValueError, match="już istnieje"):
        prepare_source(repo, destination, kind="local")
    (repo / "run.py").write_text("# changed", encoding="utf-8")
    with pytest.raises(ValueError, match="niezapisane"):
        prepare_source(repo, tmp_path / "another", kind="local")
    with pytest.raises(ValueError):
        prepare_source(repo, repo / "nested", kind="master")


@pytest.mark.parametrize("kind,value", [("pr", "-1"), ("merge", "17 --evil"), ("branch", "--upload-pack=evil"), ("branch", "../bad")])
def test_ref_inputs_cannot_be_options_or_paths(repo, tmp_path, kind, value):
    with pytest.raises(ValueError):
        prepare_source(repo, tmp_path / "refused", kind=kind, value=value)


@pytest.mark.parametrize("name", ["../outside", "/absolute", "C:/drive", "nested/../../escape", ".git/config", "MEMORY/private", "dir\\file", "file:stream"])
def test_hostile_zip_is_rejected_before_extraction(repo, tmp_path, name):
    archive = tmp_path / "source.zip"
    with zipfile.ZipFile(archive, "w") as out:
        out.writestr("run.py", "# synthetic starter")
        out.writestr("main.py", "# synthetic control plane")
        out.writestr("latka_jazn/version.py", 'PACKAGE_VERSION="1.2.3"')
        out.writestr(name, "untrusted")
    # ZipInfo normalizes the host separator on Windows. Build the literal
    # hostile wire name in both ZIP headers so this tests the reader boundary.
    if "\\" in name:
        archive.write_bytes(archive.read_bytes().replace(name.replace("\\", "/").encode(), name.encode()))
        with zipfile.ZipFile(archive) as check:
            assert name in [info.orig_filename for info in check.infolist()]
    destination = tmp_path / "extracted"
    with pytest.raises(ValueError):
        prepare_source(repo, destination, kind="zip", value=str(archive))
    assert not destination.exists()


def test_bare_zip_with_version_is_not_a_verified_system(repo, tmp_path):
    archive = tmp_path / "bare.zip"
    with zipfile.ZipFile(archive, "w") as out:
        out.writestr("run.py", "# no manifest")
        out.writestr("main.py", "# no manifest")
        out.writestr("latka_jazn/version.py", 'PACKAGE_VERSION="1.2.3"')
    with pytest.raises((OSError, ValueError)):
        prepare_source(repo, tmp_path / "bare", kind="zip", value=str(archive))


def test_zip_code_memory_package_is_distinct_from_private_memory(repo, tmp_path):
    archive = tmp_path / "code.zip"
    with zipfile.ZipFile(archive, "w") as out:
        out.writestr("SYSTEM/run.py", "# synthetic starter")
        out.writestr("SYSTEM/main.py", "# synthetic control plane")
        out.writestr("SYSTEM/latka_jazn/version.py", 'PACKAGE_VERSION="1.2.3"')
        out.writestr("SYSTEM/latka_jazn/memory/__init__.py", "# package code")
    selected = _extract_zip(archive, tmp_path / "code")
    assert selected.name == "SYSTEM"
    assert (selected / "latka_jazn/memory/__init__.py").is_file()
    assert not (selected / "memory").exists()
