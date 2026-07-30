from __future__ import annotations

from pathlib import Path
import json

from .final_export import export_final_memory
from .path_picker import choose_directory
from .tui_common import ask_text, message, run_dialog

try:  # pragma: no cover - terminal dependent
    from prompt_toolkit.shortcuts import yes_no_dialog
except Exception:  # pragma: no cover
    yes_no_dialog = None  # type: ignore[assignment]


def final_export_menu(database: Path) -> None:
    output = choose_directory(title="Wybierz katalog nadrzędny finalnego eksportu")
    if not output:
        return
    name = ask_text("Finalny eksport", "Nazwa nowego folderu eksportu:", "jazn_memory_final")
    if not name:
        return
    target = output / name
    baselines: list[Path] = []
    if run_dialog(yes_no_dialog(title="Baseline'y", text="Dodać folder z bazami Testów 01-04 do porównania?")):
        selected = choose_directory(title="Wybierz folder z baseline'ami")
        if selected:
            baselines.append(selected)
    overwrite = False
    if target.exists():
        overwrite = bool(run_dialog(yes_no_dialog(
            title="Istniejący katalog",
            text=f"{target}\n\nKatalog istnieje. Utworzyć jego backup i opublikować nowy eksport?",
        )))
        if not overwrite:
            message("Finalny eksport", "Operacja anulowana. Istniejący katalog pozostał bez zmian.")
            return
    result = export_final_memory(database, target, baselines=baselines, overwrite=overwrite)
    message("Finalny eksport", json.dumps(result, ensure_ascii=False, indent=2, default=str))


__all__ = ["final_export_menu"]
