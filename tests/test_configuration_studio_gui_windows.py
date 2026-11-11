from __future__ import annotations

import os
import sys
import subprocess
from pathlib import Path
import tkinter as tk

import pytest

from latka_jazn.tools.configuration_studio_ui import ConfigurationStudio
from latka_jazn.tools.configuration_studio import validate_values


def _real_gui_navigation_and_profile_fields(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("latka_jazn.tools.configuration_studio_ui.messagebox.askyesno", lambda *a, **k: True)
    system = tmp_path / "root"
    (system / "latka_jazn").mkdir(parents=True)
    (system / "latka_jazn" / "version.py").write_text("", encoding="utf-8")
    (system / "main.py").write_text("", encoding="utf-8")
    root = tk.Tk()
    root.withdraw()
    try:
        app = ConfigurationStudio(root, system=system)
        assert app._current_page == "overview"
        app.open_page("paths")
        assert app._current_page == "paths"
        app.open_page("settings")
        assert app._current_page == "settings"
        assert "JAZN_MEMORY_ROOT" in app._entries
        app._entries["JAZN_MEMORY_MODE"].set("optional")
        data = validate_values(system, app._values())
        assert data["JAZN_MEMORY_MODE"] == "optional"
        app.open_page("diagnostics")
        assert app._current_page == "diagnostics"
    finally:
        root.destroy()


def _gui_refuses_to_discard_unsaved_edits(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    system = tmp_path / "root"
    (system / "latka_jazn").mkdir(parents=True)
    (system / "latka_jazn" / "version.py").write_text("", encoding="utf-8")
    (system / "main.py").write_text("", encoding="utf-8")
    root = tk.Tk()
    root.withdraw()
    try:
        app = ConfigurationStudio(root, system=system)
        app.open_page("settings")
        app._entries["JAZN_MEMORY_MODE"].set("required")
        assert app._dirty() is True
        monkeypatch.setattr("latka_jazn.tools.configuration_studio_ui.messagebox.askyesno",
                            lambda *a, **kw: False)
        app.open_page("diagnostics")
        assert app._current_page == "settings"
        monkeypatch.setattr("latka_jazn.tools.configuration_studio_ui.messagebox.askyesno",
                            lambda *a, **kw: True)
        app.open_page("diagnostics")
        assert app._current_page == "diagnostics"
    finally:
        root.destroy()


def _isolated_tk_env(tmp_path: Path) -> dict[str, str]:
    """Do not inherit another pytest case's ROOT, daemon, MEMORY or TPA paths.

    These GUI scenarios create a historical synthetic ROOT at tmp_path/root.
    Do not force its sibling workspace as a global override: Memory Rebuild
    validates destinations against BOTH that synthetic ROOT and the prepared
    checkout providing this code, which refuses outside-root overrides.
    The bare ROOT resolves its sibling workspace by default. Keep an isolated
    operator state directory and Windows PATH/SystemRoot/Tcl/Tk environment.
    """
    child_env = {
        key: value
        for key, value in os.environ.items()
        if not key.upper().startswith("JAZN_")
    }
    child_env["JAZN_OPERATOR_STATE_ROOT"] = str(tmp_path / "operator_state")
    return child_env


def _run_fresh_tk(scenario: str, tmp_path: Path) -> None:
    # Tk interpreters own native thread state. Run every real operator window
    # in a fresh interpreter, as the public GUI launcher does; keep all original
    # navigation, validation and unsaved-edit assertions inside that process.
    program = """import runpy, sys
from pathlib import Path
import pytest
namespace = runpy.run_path(sys.argv[1])
with pytest.MonkeyPatch.context() as monkeypatch:
    namespace[sys.argv[2]](Path(sys.argv[3]), monkeypatch)
"""
    result = subprocess.run(
        [sys.executable, "-X", "utf8", "-c", program, str(Path(__file__).resolve()), scenario, str(tmp_path)],
        cwd=Path(__file__).resolve().parents[1], capture_output=True,
        text=True, encoding="utf-8", timeout=45, check=False,
        env=_isolated_tk_env(tmp_path),
    )
    assert result.returncode == 0, f"Tk scenario {scenario} failed: {result.stdout} {result.stderr}"


@pytest.mark.skipif(sys.platform != "win32", reason="requires Windows desktop Tk")
def test_real_gui_navigation_and_profile_fields(tmp_path: Path) -> None:
    _run_fresh_tk("_real_gui_navigation_and_profile_fields", tmp_path)


@pytest.mark.skipif(sys.platform != "win32", reason="requires Windows desktop Tk")
def test_gui_refuses_to_discard_unsaved_edits(tmp_path: Path) -> None:
    _run_fresh_tk("_gui_refuses_to_discard_unsaved_edits", tmp_path)

def test_fresh_tk_child_environment_is_scoped_to_synthetic_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The autouse checkout override must never leak into a synthetic Tk ROOT."""
    monkeypatch.setenv("JAZN_RUNTIME_WORKSPACE_DIR", "$ROOT/.settings_local/acceptance/inherited")
    monkeypatch.setenv("JAZN_MEMORY_ROOT", str(tmp_path / "private_memory"))
    monkeypatch.setenv("JAZN_STUDIO_ACCEPTANCE_PROFILE", "isolated")
    monkeypatch.setenv("JAZN_MEMORY_REBUILD_SETTINGS", str(tmp_path / "inherited.json"))
    child = _isolated_tk_env(tmp_path)
    assert "JAZN_RUNTIME_WORKSPACE_DIR" not in child
    assert child["JAZN_OPERATOR_STATE_ROOT"] == str(tmp_path / "operator_state")
    assert set(key for key in child if key.upper().startswith("JAZN_")) == {
        "JAZN_OPERATOR_STATE_ROOT",
    }



def test_fresh_tk_child_settings_path_is_valid_across_both_system_roots(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The subprocess must resolve Memory Rebuild settings without a foreign ROOT override."""
    system = tmp_path / "root"
    (system / "latka_jazn").mkdir(parents=True)
    (system / "latka_jazn" / "version.py").write_text("", encoding="utf-8")
    (system / "main.py").write_text("", encoding="utf-8")
    monkeypatch.setenv("JAZN_RUNTIME_WORKSPACE_DIR", "$ROOT/.settings_local/acceptance/parent")
    monkeypatch.setenv("JAZN_MEMORY_REBUILD_SETTINGS", str(tmp_path / "foreign_settings.json"))
    program = (
        "import sys\n"
        "from pathlib import Path\n"
        "from latka_jazn.tools.memory_rebuild_app.settings import resolve_settings_path\n"
        "print(resolve_settings_path(tool_root=Path(sys.argv[1])))\n"
    )
    result = subprocess.run(
        [sys.executable, "-X", "utf8", "-c", program, str(system)],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True, text=True, encoding="utf-8",
        timeout=30, check=False, env=_isolated_tk_env(tmp_path),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    expected = tmp_path / "operator_state" / "memory_rebuild" / "memory_rebuild_settings.json"
    assert result.stdout.strip() == str(expected.resolve())
    # Discovery and validation must remain read-only, including in the child.
    assert not expected.exists()
    assert not (tmp_path / "workspace_runtime").exists()
