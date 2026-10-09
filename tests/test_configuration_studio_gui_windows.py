from __future__ import annotations

import sys
from pathlib import Path
import tkinter as tk

import pytest

from latka_jazn.tools.configuration_studio_ui import ConfigurationStudio
from latka_jazn.tools.configuration_studio import validate_values


@pytest.mark.skipif(sys.platform != "win32", reason="requires Windows desktop Tk")
def test_real_gui_navigation_and_profile_fields(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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


@pytest.mark.skipif(sys.platform != "win32", reason="requires Windows desktop Tk")
def test_gui_refuses_to_discard_unsaved_edits(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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
