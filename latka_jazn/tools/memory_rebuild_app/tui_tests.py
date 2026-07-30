from __future__ import annotations

from pathlib import Path

from .path_picker import choose_directory
from .test_profiles import PROFILE_NAMES, run_test_profile
from .tui_common import message, run_dialog
try:  # pragma: no cover - terminal dependent
    from prompt_toolkit.shortcuts import radiolist_dialog, yes_no_dialog
except Exception:  # pragma: no cover
    radiolist_dialog = yes_no_dialog = None  # type: ignore[assignment]


def test_menu(database: Path) -> None:
    while True:
        profile = run_dialog(radiolist_dialog(
            title="Testy pamięci",
            text="Testy 01–04 są profilami zgodności. Test finalny jest ich nadzbiorem.",
            values=[(name, name.upper()) for name in PROFILE_NAMES] + [("back", "Wróć")],
        ))
        if profile in {None, "back"}:
            return
        baselines: list[Path] = []
        if profile in {"test04", "final"} and run_dialog(yes_no_dialog(title="Baseline’y", text="Dodać folder z bazami Testów 01–04?")):
            folder = choose_directory(title="Wybierz folder z baseline’ami")
            if folder:
                baselines.append(folder)
        report = run_test_profile(database, profile, baselines=baselines, full_validation=True)
        lines = [f"Profil: {profile}", f"Wynik: {'ZALICZONY' if report['ok'] else 'NIEZALICZONY'}", ""]
        for check in report["checks"]:
            mark = "✓" if check["passed"] else ("!" if not check["blocking"] else "✗")
            lines.append(f"{mark} {check['name']}: {check.get('actual')}")
        message("Wynik testu", "\n".join(lines))


__all__ = ["test_menu"]
