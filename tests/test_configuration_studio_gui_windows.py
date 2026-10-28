from __future__ import annotations

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
    )
    assert result.returncode == 0, f"Tk scenario {scenario} failed: {result.stdout} {result.stderr}"


@pytest.mark.skipif(sys.platform != "win32", reason="requires Windows desktop Tk")
def test_real_gui_navigation_and_profile_fields(tmp_path: Path) -> None:
    _run_fresh_tk("_real_gui_navigation_and_profile_fields", tmp_path)


@pytest.mark.skipif(sys.platform != "win32", reason="requires Windows desktop Tk")
def test_gui_refuses_to_discard_unsaved_edits(tmp_path: Path) -> None:
    _run_fresh_tk("_gui_refuses_to_discard_unsaved_edits", tmp_path)
