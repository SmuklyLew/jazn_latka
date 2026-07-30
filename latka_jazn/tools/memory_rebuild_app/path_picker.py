from __future__ import annotations

from pathlib import Path
from typing import Iterable


def _initial_directory(value: str | Path | None) -> str | None:
    if value is None or not str(value).strip():
        return None
    path = Path(value).expanduser()
    if path.is_file():
        path = path.parent
    while not path.exists() and path != path.parent:
        path = path.parent
    return str(path.resolve()) if path.exists() else None


def choose_files(
    *,
    title: str,
    initial_directory: str | Path | None = None,
    multiple: bool = True,
) -> list[Path]:
    """Open the native file chooser. Return an empty list when unavailable/cancelled."""

    try:
        import tkinter as tk
        from tkinter import filedialog
    except Exception:
        return []

    root = None
    try:
        root = tk.Tk()
        root.withdraw()
        try:
            root.attributes("-topmost", True)
        except Exception:
            pass
        options = {
            "title": title,
            "initialdir": _initial_directory(initial_directory),
            "filetypes": (
                ("Źródła pamięci", "*.zip *.json *.jsonl *.ndjson *.html *.htm *.txt *.md *.pdf *.docx *.odt *.rtf *.sqlite *.sqlite3 *.db *.png *.jpg *.jpeg *.webp *.gif *.bmp *.tif *.tiff *.svg"),
                ("Wszystkie pliki", "*.*"),
            ),
        }
        if multiple:
            values: Iterable[str] = filedialog.askopenfilenames(**options)
        else:
            value = filedialog.askopenfilename(**options)
            values = [value] if value else []
        return [Path(item).expanduser().resolve() for item in values if str(item).strip()]
    except Exception:
        return []
    finally:
        if root is not None:
            try:
                root.destroy()
            except Exception:
                pass


def choose_directory(
    *,
    title: str,
    initial_directory: str | Path | None = None,
) -> Path | None:
    """Open the native directory chooser. Return None when unavailable/cancelled."""

    try:
        import tkinter as tk
        from tkinter import filedialog
    except Exception:
        return None

    root = None
    try:
        root = tk.Tk()
        root.withdraw()
        try:
            root.attributes("-topmost", True)
        except Exception:
            pass
        value = filedialog.askdirectory(
            title=title,
            initialdir=_initial_directory(initial_directory),
            mustexist=True,
        )
        return Path(value).expanduser().resolve() if value else None
    except Exception:
        return None
    finally:
        if root is not None:
            try:
                root.destroy()
            except Exception:
                pass


__all__ = ["choose_directory", "choose_files"]
