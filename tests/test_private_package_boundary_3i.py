"""Prevent release packages from containing local operator settings."""

from pathlib import Path

import pytest

from latka_jazn.tools import (
    package_export,
    package_integrity,
    release_staging,
)
from latka_jazn.tools.source_provenance import SourceProvenanceError


@pytest.mark.parametrize("relative", [
    ".settings_local/operator/settings.json",
    ".settings_local/secrets/token.txt",
    ".SeTtInGs_LoCaL/acceptance/session.json",
])
def test_private_paths_forbidden(relative):
    assert package_integrity.path_is_forbidden(relative)
    assert package_export.forbidden_package_reason(relative)

    with pytest.raises(package_export.PackagePlanValidationError):
        package_export.validate_package_plan([relative])


def test_versioned_settings_remain_packagable():
    relative = ".settings/templates/first-install.example.json"

    assert not package_integrity.path_is_forbidden(relative)
    assert package_export.forbidden_package_reason(relative) is None


def test_local_settings_excluded_from_export(tmp_path):
    root = tmp_path / "source"
    root.mkdir()
    (root / "run.py").write_text("# source", encoding="utf-8")

    private = root / ".settings_local" / "operator"
    private.mkdir(parents=True)
    (private / "settings.json").write_text(
        "private", encoding="utf-8"
    )

    for mode in ("system", "github_source_safe"):
        plan = package_export.build_package_plan(root, mode)
        assert [rel for _, rel in plan] == ["run.py"]


@pytest.mark.parametrize("relative", [
    ".settings_local/operator/settings.json",
    ".SeTtInGs_LoCaL/secrets/token.txt",
])
def test_tracked_private_git_entry_is_rejected(
    tmp_path, monkeypatch, relative
):
    root = tmp_path / "source"
    root.mkdir()
    destination = tmp_path / "staging"
    head = "a" * 40

    monkeypatch.setattr(
        release_staging,
        "build_source_provenance_document",
        lambda *_args, **_kwargs: {"base_merge_commit": head},
    )

    def fake_git(_root, *args, binary=False):
        if args == ("rev-parse", "HEAD"):
            return head + "\n"
        if args[0] == "ls-tree":
            return (
                b"100644 blob " + b"b" * 40
                + b"\t" + relative.encode("utf-8") + b"\0"
            )
        raise AssertionError(f"Unexpected git command: {args}")

    monkeypatch.setattr(release_staging, "_git", fake_git)

    with pytest.raises(
        SourceProvenanceError,
        match="forbids generated/private source",
    ):
        release_staging.create_release_staging(root, destination)

    assert not (destination / ".settings_local").exists()
