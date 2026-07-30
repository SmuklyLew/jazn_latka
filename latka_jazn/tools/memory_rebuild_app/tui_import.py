from __future__ import annotations

from pathlib import Path
import json

from .path_picker import choose_directory, choose_files
from .source_browser import discover_source_files, format_discovered_files
from .tui_common import message, run_dialog
from .unified_memory import UnifiedMemoryDatabase

try:  # pragma: no cover - terminal dependent
    from prompt_toolkit.shortcuts import checkboxlist_dialog, radiolist_dialog, yes_no_dialog
except Exception:  # pragma: no cover
    checkboxlist_dialog = radiolist_dialog = yes_no_dialog = None  # type: ignore[assignment]


def source_import_menu(database: Path) -> None:
    store = UnifiedMemoryDatabase(database)
    while True:
        choice = run_dialog(radiolist_dialog(
            title="Import rozmów i pamięci",
            text=f"Baza: {database}\n\nImport jest przyrostowy; identyczne eksporty są deduplikowane.",
            values=[
                ("files", "Wybierz pliki do importu"),
                ("folder", "Przeskanuj folder i wybierz pliki"),
                ("legacy", "Połącz stare bazy Testów 01–04 z tą bazą"),
                ("back", "Wróć"),
            ],
        ))
        if choice in {None, "back"}:
            return
        if choice == "files":
            files = choose_files(title="Wybierz eksporty, HTML, dzienniki lub SQLite", multiple=True)
            if files:
                message("Wynik importu", json.dumps(store.import_sources(files, full_validation=True), ensure_ascii=False, indent=2, default=str))
        elif choice == "folder":
            folder = choose_directory(title="Wybierz folder ze źródłami")
            if not folder:
                continue
            recursive = bool(run_dialog(yes_no_dialog(title="Podfoldery", text="Skanować również podfoldery, w tym .BardzoStareCos?")))
            files = discover_source_files(folder, recursive=recursive)
            if not files:
                message("Skan folderu", "Nie znaleziono obsługiwanych plików.")
                continue
            selected = run_dialog(checkboxlist_dialog(
                title="Wybierz pliki do importu", text=format_discovered_files(folder, files),
                values=[(str(path), str(path.relative_to(folder))) for path in files],
                default_values=[str(path) for path in files],
            ))
            if selected:
                message("Wynik importu", json.dumps(store.import_sources([Path(item) for item in selected], full_validation=True), ensure_ascii=False, indent=2, default=str))
        elif choice == "legacy":
            folder = choose_directory(title="Wybierz folder zawierający bazy Testów 01–04")
            if not folder:
                continue
            dry = bool(run_dialog(yes_no_dialog(title="Najpierw plan", text="Wykonać tylko plan migracji bez zapisu?")))
            message("Migracja starych baz", json.dumps(store.migrate_legacy_root(folder, dry_run=dry), ensure_ascii=False, indent=2, default=str))


__all__ = ["source_import_menu"]
