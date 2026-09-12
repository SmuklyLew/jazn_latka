from __future__ import annotations

from pathlib import Path
import sys

from latka_jazn.tools.application_shell import (
    CommandItem,
    CommandStudioSpec,
    DiagnosticsHub,
    run_window_studio,
)

from .config import APP_VERSION


def build_studio_spec(*, tool_root: Path) -> CommandStudioSpec:
    root = Path(tool_root).expanduser().resolve()
    return CommandStudioSpec(
        app_id="jazn-memory-rebuild",
        app_name="Jaźń - Memory Rebuild",
        version=APP_VERSION,
        description=(
            "Profesjonalne Studio odbudowy i walidacji pamięci Jaźni. "
            "Wszystkie tryby korzystają z tego samego kanonicznego CLI i kontraktu diagnostycznego."
        ),
        command_prefix=(sys.executable, "-X", "utf8", str(root / "tools" / "rebuild_memory.py")),
        commands=(
            CommandItem("list-projects", "Projekty", "Pokaż zapisane projekty odbudowy pamięci."),
            CommandItem("create-project", "Nowy projekt", "Utwórz projekt odbudowy pamięci.", "--name NAZWA --target-root PATH"),
            CommandItem("show-project", "Projekt", "Pokaż konfigurację wybranego projektu.", "--project <ID|nazwa>"),
            CommandItem("add-source", "Dodaj źródło", "Dodaj i rozpoznaj źródło projektu.", "--project <ID|nazwa> PATH --approved"),
            CommandItem("add-baseline", "Dodaj baseline", "Dodaj bazę testową do porównań.", "--project <ID|nazwa> PATH"),
            CommandItem("preflight", "Preflight", "Sprawdź projekt przed operacjami zapisu.", "--project <ID|nazwa>"),
            CommandItem("test00", "Test 00", "Zweryfikuj wierność źródeł i source mirror.", "--project <ID|nazwa>"),
            CommandItem("recall-baseline", "Recall baseline", "Uruchom mierzalny FTS5-only benchmark Recall.", "--database <plik.sqlite3> --benchmark <benchmark.json>"),
            CommandItem("compare", "Porównanie", "Porównaj bazę docelową z baseline'ami projektu.", "--project <ID|nazwa>"),
            CommandItem("plan", "Plan", "Uruchom plan zgodności bez zapisu baz.", "--project <ID|nazwa>"),
            CommandItem("export", "Eksport", "Eksportuj manifest projektu lub Testu 04.", "--project <ID|nazwa> --format project --output OUT.json"),
            CommandItem("run", "Odbudowa", "Uruchom zgodnościową odbudowę po jawnym tokenie potwierdzenia.", "--project <ID|nazwa> --confirm TOKEN"),
        ),
        state_dir=Path.home() / ".jazn" / "tools" / "memory_rebuild",
        working_dir=root,
        settings_filename="ui_settings.json",
        default_ui="tui",
    )


def build_window_spec(*, tool_root: Path) -> CommandStudioSpec:
    return build_studio_spec(tool_root=tool_root)


def run_window(*, tool_root: Path, diagnostics: DiagnosticsHub) -> int:
    return run_window_studio(build_studio_spec(tool_root=tool_root), diagnostics)


__all__ = ["build_studio_spec", "build_window_spec", "run_window"]
