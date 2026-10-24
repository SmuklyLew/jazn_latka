"""Single-source version release compatibility and non-executing AST gates."""
from __future__ import annotations

import ast
import importlib
from pathlib import Path
import tomllib

import pytest

from latka_jazn.core.version_source import (
    read_version_metadata_from_version_py,
    read_version_py_assignments,
    read_version_text_assignments,
)
from latka_jazn.tools.release_metadata_sync import _literal_runtime_version
from latka_jazn.version import DISTRIBUTION_VERSION, PACKAGE_VERSION


def test_one_editable_literal_and_compatible_public_alias() -> None:
    root = Path(__file__).resolve().parents[1]
    raw = (root / "latka_jazn/version.py").read_text(encoding="utf-8")
    tree = ast.parse(raw)
    assignments = {
        target.id: node.value
        for node in tree.body if isinstance(node, ast.Assign)
        for target in node.targets if isinstance(target, ast.Name)
        and target.id in {"PACKAGE_VERSION", "DISTRIBUTION_VERSION"}
    }
    assert isinstance(assignments["PACKAGE_VERSION"], ast.Constant)
    assert isinstance(assignments["DISTRIBUTION_VERSION"], ast.Name)
    assert assignments["DISTRIBUTION_VERSION"].id == "PACKAGE_VERSION"
    assert PACKAGE_VERSION == DISTRIBUTION_VERSION
    assert read_version_py_assignments(root / "latka_jazn/version.py")["DISTRIBUTION_VERSION"] == PACKAGE_VERSION
    assert read_version_metadata_from_version_py(root).distribution_version == PACKAGE_VERSION
    pyproject = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    assert pyproject["tool"]["setuptools"]["dynamic"]["version"]["attr"] == "latka_jazn.version.PACKAGE_VERSION"


def test_alias_parsed_without_import_and_without_execution(tmp_path: Path) -> None:
    source = (
        'PACKAGE_VERSION = "16.3.25.5.116.0.34.74"\n'
        'DISTRIBUTION_VERSION = PACKAGE_VERSION\n'
        'PACKAGE_RELEASE_NAME = "single-source"\n'
        'raise RuntimeError("must not run")\n'
    )
    values = read_version_text_assignments(source)
    assert values["DISTRIBUTION_VERSION"] == values["PACKAGE_VERSION"]
    assert _literal_runtime_version(source) == "16.3.25.5.116.0.34.74-single-source"
    root = tmp_path / "source"
    (root / "latka_jazn").mkdir(parents=True)
    (root / "latka_jazn/version.py").write_text(source, encoding="utf-8")
    assert read_version_metadata_from_version_py(root).package_version_full.endswith("-single-source")


def test_unsafe_or_unresolved_alias_is_rejected() -> None:
    with pytest.raises(ValueError, match="preceding literal"):
        read_version_text_assignments('DISTRIBUTION_VERSION = PACKAGE_VERSION\nPACKAGE_VERSION = "1.2.3"\n')
    with pytest.raises(ValueError, match="preceding literal"):
        read_version_text_assignments('PACKAGE_VERSION = factory()\nDISTRIBUTION_VERSION = PACKAGE_VERSION\n')
    assert _literal_runtime_version('PACKAGE_VERSION = factory()\nDISTRIBUTION_VERSION = PACKAGE_VERSION') is None


def test_historical_two_literal_version_retains_read_support(tmp_path: Path) -> None:
    root = tmp_path / "legacy"
    (root / "latka_jazn").mkdir(parents=True)
    (root / "latka_jazn/version.py").write_text(
        'DISTRIBUTION_VERSION = "15.1.0.3"\n'
        'PACKAGE_VERSION = "v15.1.0.3.99"\n'
        'PACKAGE_RELEASE_NAME = "legacy"\n',
        encoding="utf-8",
    )
    metadata = read_version_metadata_from_version_py(root)
    assert metadata.distribution_version == "15.1.0.3"
    assert metadata.package_version_full == "v15.1.0.3.99-legacy"


def test_version_rebuild_preserves_alias_on_modern_write(tmp_path: Path) -> None:
    rebuild = importlib.import_module("tools.jazn_version_rebuild")
    path = tmp_path / "version.py"
    path.write_text(
        'PACKAGE_VERSION = "16.3.25.5.116.0.34.74"\n'
        'DISTRIBUTION_VERSION = PACKAGE_VERSION\n'
        'PACKAGE_RELEASE_NAME = "first"\n', encoding="utf-8",
    )
    data = rebuild.build_version("16.3.25.5.116.0.34.75", "", "second")
    assert data.version == data.package
    path.write_bytes(rebuild.render_version(path, data))
    result = rebuild.assignments(path)
    assert result["DISTRIBUTION_VERSION"] == result["PACKAGE_VERSION"] == data.package
    assert "DISTRIBUTION_VERSION = PACKAGE_VERSION" in path.read_text(encoding="utf-8")
    version_dir = tmp_path / "latka_jazn"
    version_dir.mkdir()
    (version_dir / "version.py").write_bytes(path.read_bytes())
    assert rebuild.read_version(tmp_path) == data


def test_version_rebuild_migrates_legacy_literal_on_new_write(tmp_path: Path) -> None:
    rebuild = importlib.import_module("tools.jazn_version_rebuild")
    path = tmp_path / "version.py"
    path.write_text(
        'DISTRIBUTION_VERSION = "16.3.25.5.116.0.34.73"\n'
        'PACKAGE_VERSION = "16.3.25.5.116.0.34.73"\n'
        'PACKAGE_RELEASE_NAME = "old"\n', encoding="utf-8",
    )
    data = rebuild.build_version("16.3.25.5.116.0.34.75", "", "new")
    rendered = rebuild.render_version(path, data).decode("utf-8")
    assert "DISTRIBUTION_VERSION = PACKAGE_VERSION" in rendered
    assert rendered.count('"16.3.25.5.116.0.34.75"') == 1
    assert rebuild.pyproject_ok is not None
