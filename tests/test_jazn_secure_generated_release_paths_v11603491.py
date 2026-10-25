"""Release regressions: never ship generated build copies or private canon.

Temporary fixture paths only. No private extension payload is read by these tests.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from latka_jazn.tools import package_export, package_integrity, release_staging
from latka_jazn.tools.source_provenance import SourceProvenanceError


@pytest.mark.parametrize("relative", [
    "build/lib/latka_jazn/version.py",
    "build/lib/latka_jazn/core/canon/local_private_canon_extension.py",
    "latka_jazn/core/canon/local_private_canon_extension.py",
    "some/other/local_private_canon_extension.py",
])
def test_generated_and_private_paths_cannot_enter_integrity_manifest(relative: str) -> None:
    assert package_integrity.path_is_forbidden(relative)


@pytest.mark.parametrize("relative", [
    "build/lib/latka_jazn/version.py",
    "build/lib/latka_jazn/core/canon/local_private_canon_extension.py",
    "latka_jazn/core/canon/local_private_canon_extension.py",
    "renamed/location/local_private_canon_extension.py",
])
def test_export_plans_reject_generated_and_private_paths(relative: str) -> None:
    assert package_export.forbidden_package_reason(relative)
    with pytest.raises(package_export.PackagePlanValidationError):
        package_export.validate_package_plan([relative])


def test_source_export_ignores_generated_tree_even_when_present(tmp_path: Path) -> None:
    source = tmp_path / "system"
    source.mkdir()
    (source / "run.py").write_text("# source\n", encoding="utf-8")
    generated = source / "build" / "lib" / "latka_jazn"
    generated.mkdir(parents=True)
    (generated / "version.py").write_text("# generated\n", encoding="utf-8")
    private = source / "latka_jazn" / "core" / "canon"
    private.mkdir(parents=True)
    (private / "local_private_canon_extension.py").write_text("# private\n", encoding="utf-8")
    for mode in ("system", "github_source_safe"):
        plan = package_export.build_package_plan(source, mode)
        assert [rel for _, rel in plan] == ["run.py"]


def test_canonical_release_staging_fails_closed_on_tracked_build(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    destination = tmp_path / "staging"
    expected_head = "a" * 40
    monkeypatch.setattr(
        release_staging, "build_source_provenance_document",
        lambda *_args, **_kwargs: {"base_merge_commit": expected_head},
    )

    def fake_git(_root: Path, *args: str, binary: bool = False) -> str | bytes:
        if args == ("rev-parse", "HEAD"):
            return expected_head + "\n"
        if args == ("rev-parse", "HEAD"):
            return expected_head + "\n"
        if args[0] == "ls-tree":
            return b"100644 blob " + b"b" * 40 + b"\tbuild/lib/latka_jazn/version.py\0"
        raise AssertionError(f"Unexpected Git request: {args!r}")

    monkeypatch.setattr(release_staging, "_git", fake_git)
    with pytest.raises(SourceProvenanceError, match="forbids generated/private source"):
        release_staging.create_release_staging(root, destination)
    assert not (destination / "build").exists()
