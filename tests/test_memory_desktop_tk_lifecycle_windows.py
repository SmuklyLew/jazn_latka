"""Windows regression: two complete native Studio windows in either order.

No global gc.collect(), test skips on supported Windows or altered assertions.
The application itself must cancel its owned polling callbacks on Tk destroy.
"""
from __future__ import annotations

import sys
from pathlib import Path
import tkinter as tk
from tkinter import ttk

import pytest

from latka_jazn.tools.application_shell import DiagnosticsHub
from latka_jazn.tools.memory_rebuild_app.ui_desktop import DesktopWorkspace, PAGES


pytestmark = pytest.mark.skipif(
    sys.platform != "win32", reason="native Windows desktop Tk required"
)


def _exercise_pages(app: DesktopWorkspace, root: tk.Tk) -> None:
    for page, label, _hint in PAGES:
        app.open_page(page)
        root.update_idletasks()
        assert app.heading.cget("text") == label
    assert app._page == "diagnostics"


def _exercise_actions(app: DesktopWorkspace) -> None:
    def find_button(name: str) -> ttk.Button:
        for frame in app.content.winfo_children():
            for widget in frame.winfo_children():
                if isinstance(widget, ttk.Button) and widget.cget("text") == name:
                    return widget
        pytest.fail(f"Missing home action: {name}")

    find_button("Otwórz projekt").invoke()
    assert app._page == "projects"
    app.open_page("home")
    find_button("Skonfiguruj ścieżki").invoke()
    assert app._page == "paths"


@pytest.mark.parametrize(
    "order",
    [("pages", "actions"), ("actions", "pages")],
    ids=("pages-then-actions", "actions-then-pages"),
)
def test_two_windows_release_owned_callbacks_without_gc(
    tmp_path: Path, order: tuple[str, str]
) -> None:
    for index, scenario in enumerate(order):
        root = tk.Tk()
        root.withdraw()
        app: DesktopWorkspace | None = None
        scheduled: set[str] = set()
        try:
            working = tmp_path / f"window-{index}"
            app = DesktopWorkspace(
                root, tool_root=working, project_root=working / "projects",
                settings_path=working / "settings.json",
                diagnostics=DiagnosticsHub(
                    f"tk-lifecycle-{scenario}", working / "logs", enabled=False
                ),
            )
            if scenario == "pages":
                _exercise_pages(app, root)
            else:
                _exercise_actions(app)
            scheduled = {
                timer for timer in (app._updates_after_id, app.dialogs._drain_after_id)
                if timer is not None
            }
            assert len(scheduled) == 2
        finally:
            # Deliberately bypass WM_DELETE_WINDOW as existing tests do.
            root.destroy()
        assert app is not None
        assert app._closed and app.dialogs._closed
        assert app._updates_after_id is None
        assert app.dialogs._drain_after_id is None
        assert not scheduled.intersection(set(root.tk.call("after", "info")))
        del app, root
