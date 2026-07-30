from __future__ import annotations

from pathlib import Path
import json
import os

from .path_picker import choose_directory, choose_files
from .project_store import ProjectStore
from .tui import run_studio as run_project_studio
from .tui_candidates import candidate_menu
from .tui_common import HAS_PROMPT_TOOLKIT, database_from_project, format_stats, message, run_dialog
from .tui_export import final_export_menu
from .tui_import import source_import_menu
from .tui_paths import choose_database
from .tui_tests import test_menu
from .unified_memory import CANONICAL_DATABASE_NAME, UnifiedMemoryDatabase

if HAS_PROMPT_TOOLKIT:  # pragma: no cover - terminal dependent
    from prompt_toolkit.shortcuts import radiolist_dialog


def _default_database(project_root: str | Path | None, project: str | None) -> Path:
    configured = database_from_project(project_root, project)
    if configured:
        return configured
    env = os.getenv("JAZN_MEMORY_DATABASE", "").strip()
    if env:
        return Path(env).expanduser().resolve()
    return (Path.home() / ".jazn" / CANONICAL_DATABASE_NAME).resolve()


def _remember_database(project_root: str | Path | None, project: str | None, database: Path) -> None:
    if not project:
        return
    try:
        store = ProjectStore(project_root)
        loaded = store.load(project)
        loaded.settings["unified_database_path"] = str(database)
        store.save(loaded)
    except Exception:
        return


def _text_menu(database: Path, *, project_root: str | Path | None, project: str | None, tool_root: Path) -> int:
    while True:
        print("\n=== Jaźń Memory Rebuild v2.4 ===")
        print(f"Baza: {database}")
        print("1. Projekty, źródła i baseline'y")
        print("2. Ustaw ścieżkę memory_jazn.sqlite3")
        print("3. Utwórz / sprawdź bazę")
        print("4. Importuj źródła")
        print("5. Migruj stare bazy Testów 01-04")
        print("6. Kandydaci pamięci")
        print("7. Testy 01-04 i finalny")
        print("8. Finalny eksport")
        print("9. Zakończ")
        choice = input("> ").strip()
        if choice == "1":
            run_project_studio(project_root=project_root, project=project, tool_root=tool_root, text_ui=True)
        elif choice == "2":
            raw = input(f"Ścieżka [{database}]: ").strip()
            if raw:
                database = Path(raw).expanduser().resolve()
                _remember_database(project_root, project, database)
        elif choice == "3":
            store = UnifiedMemoryDatabase(database)
            store.initialize()
            print(json.dumps(store.validate(full=True), ensure_ascii=False, indent=2, default=str))
        elif choice == "4":
            raw = input("Ścieżki plików oddzielone średnikami: ").strip()
            paths = [Path(item.strip()) for item in raw.split(";") if item.strip()]
            if paths:
                print(json.dumps(UnifiedMemoryDatabase(database).import_sources(paths), ensure_ascii=False, indent=2, default=str))
        elif choice == "5":
            raw = input("Folder ze starymi bazami: ").strip()
            if raw:
                print(json.dumps(UnifiedMemoryDatabase(database).migrate_legacy_root(raw), ensure_ascii=False, indent=2, default=str))
        elif choice == "6":
            print(json.dumps({"candidates": UnifiedMemoryDatabase(database).list_candidates(status="all", limit=500)}, ensure_ascii=False, indent=2, default=str))
        elif choice == "7":
            profile = input("Profil [test01/test02/test03/test04/final]: ").strip() or "final"
            from .test_profiles import run_test_profile
            print(json.dumps(run_test_profile(database, profile), ensure_ascii=False, indent=2, default=str))
        elif choice == "8":
            raw = input("Nowy katalog finalnego eksportu: ").strip()
            if raw:
                from .final_export import export_final_memory
                print(json.dumps(export_final_memory(database, raw), ensure_ascii=False, indent=2, default=str))
        elif choice == "9":
            return 0


def run_studio_v24(
    *,
    project_root: str | Path | None = None,
    project: str | None = None,
    tool_root: str | Path | None = None,
    text_ui: bool = False,
) -> int:
    root = Path(tool_root or Path.cwd()).expanduser().resolve()
    database = _default_database(project_root, project)
    if text_ui or not HAS_PROMPT_TOOLKIT:
        return _text_menu(database, project_root=project_root, project=project, tool_root=root)

    while True:
        store = UnifiedMemoryDatabase(database)
        exists = database.is_file()
        choice = run_dialog(radiolist_dialog(
            title="Jaźń Memory Rebuild v2.4",
            text=(
                f"Kanoniczna baza: {database}\n"
                f"Stan: {'istnieje' if exists else 'jeszcze nie utworzona'}\n\n"
                "Jedna fizyczna baza przechowuje rozmowy archiwalne i nowe, dziennik, kandydatów, "
                "doświadczenia oraz kontrolowane warstwy L1/L2/L3."
            ),
            values=[
                ("project", "1. Projekty, listy źródeł i baseline'y"),
                ("database", "2. Wybierz lub utwórz memory_jazn.sqlite3"),
                ("status", "3. Stan i integralność bazy"),
                ("import", "4. Import rozmów, HTML, dzienników i nowych wątków"),
                ("candidates", "5. Kandydaci pamięci: podgląd, edycja i decyzje"),
                ("tests", "6. Profile Testów 01, 02, 03, 04 i finalny"),
                ("export", "7. Finalny eksport stagingowy"),
                ("exit", "8. Zakończ"),
            ],
        ))
        if choice in {None, "exit"}:
            return 0
        if choice == "project":
            run_project_studio(project_root=project_root, project=project, tool_root=root, text_ui=False)
        elif choice == "database":
            selected = choose_database(database)
            if selected:
                database = selected
                _remember_database(project_root, project, database)
        elif choice == "status":
            result = store.initialize()
            result = store.validate(full=True)
            message("Stan zunifikowanej pamięci", format_stats(result))
        elif choice == "import":
            source_import_menu(database)
        elif choice == "candidates":
            candidate_menu(database)
        elif choice == "tests":
            test_menu(database)
        elif choice == "export":
            final_export_menu(database)


__all__ = ["run_studio_v24"]
