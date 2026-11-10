"""Native Windows Tk sequential Studio windows retain no scheduled Tcl callbacks."""
from __future__ import annotations

from pathlib import Path
import sys
import tkinter as tk
from tkinter import ttk

import pytest

from latka_jazn.tools.application_shell import DiagnosticsHub
from latka_jazn.tools.memory_rebuild_app.ui_desktop import DesktopWorkspace, PAGES


@pytest.mark.skipif(sys.platform != "win32", reason="native Windows Tcl/Tk required")
@pytest.mark.parametrize("order", [("pages", "actions"), ("actions", "pages")])
def test_windows_studio_sessions_cleanly_release_callbacks_in_both_orders(
    tmp_path: Path, order: tuple[str, str],
) -> None:
    # Deliberately run two real Tk interpreters in one pytest process, without
    # gc.collect(), subprocess isolation, skip, or xfail.
    for index, mode in enumerate(order):
        root = tk.Tk()
        root.withdraw()
        app = None
        try:
            work = tmp_path / str(index)
            app = DesktopWorkspace(
                root,
                tool_root=work,
                project_root=work / "projects",
                settings_path=work / "settings.json",
                diagnostics=DiagnosticsHub(
                    f"tk-lifecycle-{index}", work / "logs", enabled=False,
                ),
            )
            if mode == "pages":
                for key, label, _description in PAGES:
                    app.open_page(key)
                    root.update_idletasks()
                    assert app.heading.cget("text") == label
                assert app._page == "diagnostics"
            else:
                assert app is not None

                def button(label: str, workspace: DesktopWorkspace) -> ttk.Button:
                    for frame in workspace.content.winfo_children():
                        for widget in frame.winfo_children():
                            if isinstance(widget, ttk.Button) and widget.cget("text") == label:
                                return widget
                    pytest.fail(f"Missing quick-action button: {label}")

                button("Otwórz projekt", app).invoke()
                assert app._page == "projects"
                app.open_page("home")
                button("Skonfiguruj ścieżki", app).invoke()
                assert app._page == "paths"
        finally:
            root.destroy()
            if app is not None:
                assert app._closed
                assert app.dialogs._closed
                assert app._updates_after_id is None
                assert app.dialogs._drain_after_id is None
        del app, root
