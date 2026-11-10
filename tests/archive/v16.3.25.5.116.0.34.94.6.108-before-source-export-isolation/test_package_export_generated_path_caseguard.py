"""Reject generated build aliases irrespective of host path case rules."""
from __future__ import annotations

from pathlib import Path

import pytest

from latka_jazn.tools import package_export, package_integrity


@pytest.mark.parametrize("relative", [
    "build/lib/latka_jazn/version.py",
    "Build/lib/latka_jazn/version.py",
    "BUILD/lib/latka_jazn/version.py",
    "bUiLd/lib/latka_jazn/version.py",
])
def test_explicit_plans_reject_case_variant_build_roots(relative: str) -> None:
    assert package_export.forbidden_package_reason(relative) is not None
    assert package_integrity.path_is_forbidden(relative)
    with pytest.raises(package_export.PackagePlanValidationError):
        package_export.validate_package_plan([relative])


def test_system_export_does_not_include_mixed_case_build_tree(tmp_path: Path) -> None:
    root = tmp_path / "SYSTEM"
    (root / "BuIlD" / "lib" / "latka_jazn").mkdir(parents=True)
    (root / "BuIlD" / "lib" / "latka_jazn" / "version.py").write_text(
        "PACKAGE_VERSION = 'stale'\n", encoding="utf-8",
    )
    (root / "run.py").write_text("# canonical\n", encoding="utf-8")
    for mode in ("system", "github_source_safe"):
        paths = [rel for _path, rel in package_export.build_package_plan(root, mode)]
        assert paths == ["run.py"]
