from __future__ import annotations

from pathlib import Path
import json
import os

from latka_jazn.version import PACKAGE_VERSION

from .project_store import ProjectStore
from .studio_v16314 import run_studio_v16314
from .tui import run_studio as run_project_studio
from .unified_memory import CANONICAL_DATABASE_NAME, UnifiedMemoryDatabase


def _default_database(project_root: str | Path | None, project: str | None) -> Path:
    if project:
        try:
            loaded = ProjectStore(project_root).load(project)
            configured = str(loaded.settings.get("unified_database_path") or "").strip()
            if configured:
                return Path(configured).expanduser().resolve()
            if loaded.target_root:
                return (Path(loaded.target_root).expanduser().resolve() / CANONICAL_DATABASE_NAME).resolve()
        except Exception:
            pass
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
        print(f"\n=== Jaźń Memory Rebuild v{PACKAGE_VERSION} ===")
        print(f"Baza: {database}")
        print("1. Projekty, źródła i baseline'y")
        print("2. Ustaw ścieżkę memory_jazn.sqlite3")
        print("3. Utwórz / sprawdź bazę")
        print("4. Importuj źródła")
        print("5. Migruj stare bazy Testów 01-04")
        print("6. Kandydaci pamięci")
        print("7. Testy 00-04 i Final")
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
            profile = input("Profil [test00/test01/test02/test03/test04/final]: ").strip() or "final"
            if profile == "test00":
                raw = input("Źródła Test00 (ścieżki oddzielone średnikami): ").strip()
                sources = [Path(item.strip()) for item in raw.split(";") if item.strip()]
                if sources:
                    from .source_fidelity import default_test00_root, run_test00_source_fidelity
                    print(json.dumps(
                        run_test00_source_fidelity(sources, output_root=default_test00_root(tool_root)),
                        ensure_ascii=False,
                        indent=2,
                        default=str,
                    ))
            else:
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
    settings_path: str | Path | None = None,
) -> int:
    root = Path(tool_root or Path.cwd()).expanduser().resolve()
    database = _default_database(project_root, project)
    if text_ui:
        return _text_menu(database, project_root=project_root, project=project, tool_root=root)

    try:
        import prompt_toolkit  # noqa: F401
    except Exception:
        return _text_menu(database, project_root=project_root, project=project, tool_root=root)

    return run_studio_v16314(
        database=database,
        project_root=project_root,
        project=project,
        tool_root=root,
        settings_path=settings_path,
    )


__all__ = ["run_studio_v24"]
