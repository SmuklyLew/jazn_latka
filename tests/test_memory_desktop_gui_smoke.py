"""Smoke-render every native Studio screen on Windows without private data."""
from __future__ import annotations

from pathlib import Path
import sys
import pytest

pytest.importorskip("tkinter")


@pytest.mark.skipif(sys.platform != "win32", reason="native Windows Tk display required")
def test_native_memory_studio_renders_each_page(tmp_path: Path) -> None:
    import tkinter as tk
    from latka_jazn.tools.application_shell import DiagnosticsHub
    from latka_jazn.tools.memory_rebuild_app.ui_desktop import DesktopWorkspace, PAGES

    root = tk.Tk()
    root.withdraw()
    try:
        app = DesktopWorkspace(
            root, tool_root=tmp_path, project_root=tmp_path / "projects",
            settings_path=tmp_path / "settings.json",
            diagnostics=DiagnosticsHub("memory-studio-smoke", tmp_path / "logs", enabled=False),
        )
        for key, label, _description in PAGES:
            app.open_page(key)
            root.update_idletasks()
            assert app.heading.cget("text") == label
        assert app._page == "diagnostics"
    finally:
        root.destroy()
