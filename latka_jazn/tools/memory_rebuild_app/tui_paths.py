from __future__ import annotations

from pathlib import Path

from .path_picker import choose_directory, choose_files
from .tui_common import HAS_PROMPT_TOOLKIT, ask_text, run_dialog
from .unified_memory import CANONICAL_DATABASE_NAME

radiolist_dialog = None
if HAS_PROMPT_TOOLKIT:  # pragma: no cover
    from prompt_toolkit.shortcuts import radiolist_dialog


def choose_database(current: Path | None = None) -> Path | None:
    values = [
        ("existing", "Wybierz istniejący memory_jazn.sqlite3"),
        ("new", "Utwórz nową bazę w wybranym folderze"),
        ("type", "Wpisz pełną ścieżkę ręcznie"),
        ("cancel", "Wróć"),
    ]
    if HAS_PROMPT_TOOLKIT and radiolist_dialog is not None:
        choice = run_dialog(radiolist_dialog(
            title="Zunifikowana baza pamięci",
            text=f"Bieżąca baza: {current or 'nie wybrano'}\nWybierz sposób ustawienia ścieżki.",
            values=values,
        ))
    else:
        for index, (_, label) in enumerate(values, 1):
            print(f"{index}. {label}")
        raw = input("> ").strip()
        choice = values[int(raw) - 1][0] if raw.isdigit() and 1 <= int(raw) <= len(values) else "cancel"
    if choice == "existing":
        selected = choose_files(title="Wybierz memory_jazn.sqlite3", initial_directory=current.parent if current else None, multiple=False)
        return selected[0] if selected else current
    if choice == "new":
        folder = choose_directory(title="Wybierz folder dla memory_jazn.sqlite3", initial_directory=current.parent if current else None)
        return folder / CANONICAL_DATABASE_NAME if folder else current
    if choice == "type":
        value = ask_text("Ścieżka bazy", "Pełna ścieżka pliku memory_jazn.sqlite3:", str(current or Path.home() / ".jazn" / CANONICAL_DATABASE_NAME))
        return Path(value).expanduser().resolve() if value else current
    return current


__all__ = ["choose_database"]
