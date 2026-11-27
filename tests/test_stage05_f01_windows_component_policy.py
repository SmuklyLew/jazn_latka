"""F01/F07: Windows name policy stays fail-closed without deprecated pathlib APIs."""
from __future__ import annotations

from pathlib import Path, PureWindowsPath

import pytest

from latka_jazn.core.dedicated_private_context import (
    private_child, windows_path_component_reserved,
)
from latka_jazn.core.runtime_root import _windows_dos_comparison_path


@pytest.mark.filterwarnings("error::DeprecationWarning")
@pytest.mark.parametrize("part", [
    "NUL", "nul .txt", "CON", "conin$", "CONOUT$", "PRN", "AUX",
    "COM1.log", "LPT9", "COM¹", "lpt².txt", "COM³.log",
    "state.", "state ", "state:stream", "state?db", "state*db",
    "state|db", "state<db", "state>db", 'state"db', "state\x01db",
])
def test_reserved_windows_leaf_refused_by_both_boundaries(tmp_path: Path, part: str) -> None:
    assert windows_path_component_reserved(part) is True
    assert _windows_dos_comparison_path(PureWindowsPath("D:/system") / part) is None
    with pytest.raises(ValueError, match="private_context_path_component_invalid"):
        private_child(tmp_path, tmp_path / part)
    assert not list(tmp_path.iterdir())


@pytest.mark.filterwarnings("error::DeprecationWarning")
@pytest.mark.parametrize("part", ["", ".", "..", "nested/name", r"nested\name", "a\x00b", "a:b"])
def test_single_component_predicate_rejects_non_leaf_or_control(part: str) -> None:
    assert windows_path_component_reserved(part) is True


@pytest.mark.filterwarnings("error::DeprecationWarning")
@pytest.mark.parametrize("part", [
    "workspace", "memory.sqlite3", "scope#50%", "scope%20",
    "zażółć gęślą", ".settings_local", "COM10", "NUL-data",
])
def test_literal_valid_windows_leaf_is_preserved(tmp_path: Path, part: str) -> None:
    assert windows_path_component_reserved(part) is False
    ordinary = PureWindowsPath("D:/system") / part
    extended = PureWindowsPath(r"\\?\D:\system") / part
    assert _windows_dos_comparison_path(ordinary) == ordinary
    assert _windows_dos_comparison_path(extended) == ordinary
    assert private_child(tmp_path, tmp_path / part) == tmp_path / part
    assert not list(tmp_path.iterdir())
