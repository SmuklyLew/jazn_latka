"""F01: mixed Windows DOS path spelling must not bypass or falsely trip ROOT containment."""
from __future__ import annotations

import os
from pathlib import Path, PureWindowsPath

import pytest

from latka_jazn.core.runtime_root import (
    _windows_dos_comparison_path, workspace_runtime_path,
)


def test_dos_comparison_only_normalizes_the_drive_alias() -> None:
    ordinary = PureWindowsPath(r"D:\system\workspace")
    extended = PureWindowsPath(r"\\?\D:\system\workspace")
    assert _windows_dos_comparison_path(ordinary) == ordinary
    assert _windows_dos_comparison_path(extended) == ordinary


@pytest.mark.parametrize("value", [
    r"\\?\UNC\server\share\system",
    r"\\?\Volume{test}\system",
    r"\\.\D:\system",
    r"D:\system\..\outside",
    r"\\?\D:\system.\workspace",
    r"\\?\D:\system \workspace",
    r"\\?\D:\system\NUL",
    r"\\?\D:\system\workspace:stream",
    r"D:relative",
])
def test_ambiguous_namespaces_or_components_are_not_aliases(value: str) -> None:
    assert _windows_dos_comparison_path(PureWindowsPath(value)) is None


@pytest.mark.skipif(os.name != "nt", reason="Native Windows path identity required")
@pytest.mark.parametrize("case", ["child", "outside", "root"])
def test_workspace_resolver_mixed_dos_spelling(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case: str,
) -> None:
    root = tmp_path / "system"
    workspace = root / "state"
    workspace.mkdir(parents=True)
    (root / "local_resources").mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    original = type(root).resolve
    expected = workspace.resolve()
    target = {"child": expected, "outside": outside.resolve(), "root": root.resolve()}[case]

    def mixed(self: Path, strict: bool = False) -> Path:
        result = original(self, strict=strict)
        if result == expected:
            return Path("\\\\?\\" + str(target))
        return result

    monkeypatch.setattr(type(root), "resolve", mixed)
    if case == "child":
        result = workspace_runtime_path(root, "$ROOT/state")
        assert result.samefile(workspace)
    else:
        with pytest.raises(ValueError, match="workspace_escapes_root"):
            workspace_runtime_path(root, "$ROOT/state")


def test_workspace_real_escape_still_refused(tmp_path: Path) -> None:
    root = tmp_path / "system"
    (root / "local_resources").mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    with pytest.raises(ValueError, match="workspace_escapes_root"):
        workspace_runtime_path(root, outside)
    with pytest.raises(ValueError, match="unsafe_root_relative_workspace"):
        workspace_runtime_path(root, "$ROOT/../outside")
