"""Native Windows regression: large source inventories must remain selectable."""
from __future__ import annotations

import sys
import tkinter as tk
from tkinter import ttk

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="native Windows Tk required")

from latka_jazn.tools.memory_rebuild_app.ui_desktop import TkStudioDialogs


def _descendants(widget: tk.Misc):
    for child in widget.winfo_children():
        yield child
        yield from _descendants(child)


def test_picker_keeps_buttons_visible_for_113_files_and_supports_click_toggle() -> None:
    root = tk.Tk()
    root.withdraw()
    dialogs = TkStudioDialogs(root)
    values = [(f"file-{number}", f"export/file-{number:03d}.json") for number in range(113)]
    long_inventory = (
        "Folder: D:/synthetic-memory\nZnalezione pliki: 113\n"
        + "\n".join(f"  • export/file-{number:03d}.json" for number in range(113))
    )
    errors: list[str] = []

    def exercise() -> None:
        dialogs_found = [w for w in root.winfo_children() if isinstance(w, tk.Toplevel)]
        if not dialogs_found:
            errors.append("Source selection dialog was not created")
            return
        window = dialogs_found[0]
        try:
            window.update_idletasks()
            descendants = list(_descendants(window))
            text_widgets = [w for w in descendants if isinstance(w, tk.Text)]
            listboxes = [w for w in descendants if isinstance(w, tk.Listbox)]
            buttons = {
                str(w.cget("text")): w for w in descendants if isinstance(w, ttk.Button)
            }
            assert len(text_widgets) == 1, "Long source details must be scrollable"
            assert len(listboxes) == 1
            assert {"Wszystkie", "Żadne", "Wybierz", "Anuluj"} <= buttons.keys()
            items = listboxes[0]
            assert items.winfo_height() >= 80
            assert str(items.cget("selectmode")) == tk.MULTIPLE
            assert len(items.curselection()) == 113
            bottom = window.winfo_rooty() + window.winfo_height()
            assert all(
                button.winfo_rooty() + button.winfo_height() <= bottom
                for button in buttons.values()
            ), "Selection buttons are clipped below dialog"
            buttons["Żadne"].invoke()
            assert not items.curselection()
            items.selection_set(1)
            items.selection_set(5)
            items.event_generate("<<ListboxSelect>>")
            buttons["Wybierz"].invoke()
        except Exception as exc:
            errors.append(repr(exc))
        finally:
            if window.winfo_exists():
                window.destroy()

    root.after(150, exercise)
    try:
        selected = dialogs._pick(
            "WYBIERZ ŹRÓDŁA", long_inventory, values,
            default=[key for key, _label in values], multiple=True,
        )
        assert not errors, errors
        assert selected == ["file-1", "file-5"]
    finally:
        root.destroy()
