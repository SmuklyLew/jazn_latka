"""Windows: invoke real home quick-navigation buttons, not just page renderers."""
from __future__ import annotations

from pathlib import Path
import sys
import tkinter as tk
from tkinter import ttk

import pytest

from latka_jazn.tools.application_shell import DiagnosticsHub
from latka_jazn.tools.memory_rebuild_app.ui_desktop import DesktopWorkspace


@pytest.mark.skipif(sys.platform != "win32", reason="native Windows Tk required")
def test_home_quick_actions_navigate_real_widgets(tmp_path: Path) -> None:
    root = tk.Tk()
    root.withdraw()
    try:
        app = DesktopWorkspace(
            root, tool_root=tmp_path, project_root=tmp_path / "projects",
            settings_path=tmp_path / "settings.json",
            diagnostics=DiagnosticsHub("memory-actions", tmp_path / "logs", enabled=False),
        )

        def button(label: str) -> ttk.Button:
            for frame in app.content.winfo_children():
                for widget in frame.winfo_children():
                    if isinstance(widget, ttk.Button) and widget.cget("text") == label:
                        return widget
            pytest.fail(f"Missing quick-action button: {label}")

        button("Otwórz projekt").invoke()
        assert app._page == "projects"
        app.open_page("home")
        button("Skonfiguruj ścieżki").invoke()
        assert app._page == "paths"
    finally:
        root.destroy()
