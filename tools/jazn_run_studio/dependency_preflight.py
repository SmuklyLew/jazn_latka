"""Dependency preflight before importing Qt or the Studio controller.

Uses the canonical Jaźń profile resolver; never treats optional capabilities as
mandatory startup requirements and never starts/stops Jaźń or touches MEMORY.
"""
from __future__ import annotations

import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tomllib

ROOT = Path(__file__).resolve().parents[2]
INDEX = "https://pypi.org/simple"
ESSENTIAL = ("core", "run-studio")
HELP = {"--help", "-h", "--version", "--check", "--run", "--probe", "--gui-smoke", "--isolated-acceptance"}


def _common():
    # This module has a stdlib-only bootstrap path if packaging is absent.
    from latka_jazn.dependencies import common
    return common


def _root(args: list[str]) -> Path:
    for i, value in enumerate(args):
        if value == "--root" and i + 1 < len(args):
            return Path(args[i + 1]).expanduser().resolve()
        if value.startswith("--root="):
            return Path(value.split("=", 1)[1]).expanduser().resolve()
    return ROOT


def _profiles(root: Path) -> list[str]:
    registry = _common().load_profile_registry(root)
    # 'all' is an aggregate, not a separate capability.
    return [name for name in registry["profiles"] if name != "all"]


def inspect(root: Path) -> dict:
    """Inspect every declared dependency profile without importing optional libs."""
    common = _common()
    profile_names = _profiles(root)
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    supported = sys.version_info >= (3, 12)
    if not supported:
        raise RuntimeError("Python >=3.12 is required by pyproject.toml")
    all_rows: dict[str, list[dict]] = {}
    for name in profile_names:
        requirements = common.resolve_profile_requirements(root, [name])
        statuses = common.inspect_current_requirements(root, requirements)
        group = []
        for status in statuses:
            if status.installed_version is None:
                state = "MISSING"
            elif status.version_satisfies is False:
                state = "INCOMPATIBLE"
            elif status.version_satisfies is None:
                state = "UNKNOWN"
            elif not status.import_available:
                state = "IMPORT_MISSING"
            else:
                state = "PASS"
            group.append({
                "distribution": status.distribution,
                "requirement": status.requirement,
                "version": status.installed_version,
                "state": state,
                "import_name": status.import_name,
            })
        all_rows[name] = group
    # All optional profiles are visible, but only these block starting the GUI.
    core = {row["distribution"]: row for name in ESSENTIAL for row in all_rows.get(name, [])}
    issues = [row for row in core.values() if row["state"] != "PASS"]
    return {"profiles": all_rows, "required_issues": issues, "interpreter": sys.executable}


def _pip_check() -> tuple[str, str]:
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "--isolated", "check"],
            capture_output=True, text=True, timeout=30, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return "UNKNOWN", type(exc).__name__
    message = ((result.stdout or "") + (result.stderr or "")).strip()
    return ("PASS" if result.returncode == 0 else "BROKEN"), message[:5000]


PROFILE_LABELS = {
    "core": "Podstawowy silnik",
    "run-studio": "Graficzne Serce Systemu",
    "archive": "Archiwa",
    "studio": "Interfejs tekstowy",
    "memory-cloud": "Pamięć chmurowa (klient)",
    "memory-cloud-server": "Pamięć chmurowa (serwer)",
    "polish-nlp": "Polskie NLP",
    "mcp-http": "Połączenie MCP/HTTP",
    "pdf": "Dokumenty PDF",
}
STATUS_LABELS = {
    "PASS": "OK", "MISSING": "BRAK", "INCOMPATIBLE": "ZŁA WERSJA",
    "IMPORT_MISSING": "BRAK IMPORTU", "UNKNOWN": "NIEUSTALONE",
}


def show(report: dict, *, full: bool) -> None:
    """Plain-text accessible overview; package details only when requested."""
    profiles = report["profiles"]
    print("\n" + "=" * 56)
    print(" JAŹŃ — SPRAWDZANIE BIBLIOTEK")
    print("=" * 56)
    print("Interpreter: " + report["interpreter"])
    print("\nA. WYMAGANE DO URUCHOMIENIA STUDIO")
    print("  " + ("[GOTOWE] Można uruchomić GUI." if not report["required_issues"]
          else "[NAPRAWA] Brakuje lub nie pasują biblioteki niezbędne dla GUI."))
    for mandatory in (True, False):
        if not mandatory:
            print("\nB. DODATKOWE FUNKCJE — NIE BLOKUJĄ GUI")
        for name, rows in profiles.items():
            if (name in ESSENTIAL) != mandatory:
                continue
            good = sum(row["state"] == "PASS" for row in rows)
            print(f"  [{'OK' if good == len(rows) else 'BRAKI'}] "
                  f"{PROFILE_LABELS.get(name, name)} ({name}): {good}/{len(rows)}")
            if full or (mandatory and good != len(rows)):
                for row in rows:
                    if full or row["state"] != "PASS":
                        version = f"  (zainstalowano: {row['version']})" if row["version"] else ""
                        print(f"      [{STATUS_LABELS.get(row['state'], row['state'])}] "
                              f"{row['requirement']}{version}")
    state, message = _pip_check()
    print("\nC. SPÓJNOŚĆ JUŻ ZAINSTALOWANYCH PAKIETÓW")
    print(f"  pip check: [{state}]"
          + (f" {message}" if state != "PASS" else " Brak wykrytych konfliktów."))
    print("  To nie potwierdza instalacji opcjonalnych profili.")
    print("  Szczegóły pakietów: opcja [3] w menu.")
    print("  To nie jest test działania daemona, MEMORY, DLL ani modelu.")

def _interactive() -> bool:
    return bool(sys.stdin and sys.stdout and sys.stdin.isatty() and sys.stdout.isatty())


def _install(root: Path, profiles: list[str], *, ui: str = "text") -> bool:
    if getattr(sys, "frozen", False) or sys.prefix == sys.base_prefix:
        print("Odmowa: instalacja do środowiska globalnego/frozen jest niedozwolona.")
        return False
    common = _common()
    requirements = common.resolve_profile_requirements(root, profiles)
    statuses = common.inspect_current_requirements(root, requirements)
    wanted = [s.requirement for s in statuses if not s.ready]
    if not wanted:
        print("Brak pakietów do instalacji w wybranym profilu.")
        return True
    print("\nInterpreter: " + sys.executable)
    print("Oficjalny indeks: " + INDEX)
    print("Do instalacji / uzgodnienia wersji:")
    for item in wanted:
        print("  - " + item)
    print("Pip rozwiąże również zależności pośrednie w tym samym venv.")
    print("Uwaga: PyPI przez HTTPS nie oznacza instalacji z hash-locked wheelhouse.")
    print("Profil 'polish-nlp' może być duży. Nie instaluj go, jeśli nie jest potrzebny.")
    if ui == "tui":
        from prompt_toolkit.shortcuts import button_dialog
        try:
            decision = button_dialog(
                title="Jaźń | Zgoda na instalację",
                text=("Interpreter: " + sys.executable + "\nŹródło: " + INDEX +
                      "\n\nWybrane wymagania:\n" + "\n".join(wanted) +
                      "\n\nPip może doinstalować zależności pośrednie."),
                buttons=[("TAK — instaluj", True), ("Nie, anuluj", False)],
            ).run()
        except (EOFError, KeyboardInterrupt):
            return False
        if decision is not True:
            print("Anulowano — pip nie został uruchomiony.")
            return False
    else:
        try:
            accepted = input("Wpisz TAK, aby uruchomić pip dla tej listy: ").strip()
        except (EOFError, KeyboardInterrupt):
            return False
        if accepted.casefold() != "tak":
            print("Anulowano — pip nie został uruchomiony.")
            return False
    cmd = [sys.executable, "-m", "pip", "--isolated", "--require-virtualenv",
           "install", "--index-url", INDEX, "--only-binary=:all:",
           "--no-input", *wanted]
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith("PIP_")}
    env["PIP_CONFIG_FILE"] = os.devnull
    try:
        result = subprocess.run(cmd, cwd=root, env=env, shell=False,
                                check=False, timeout=1800)
    except (OSError, subprocess.TimeoutExpired) as exc:
        print("Instalacja nieudana: " + type(exc).__name__)
        return False
    if result.returncode:
        print("pip zwrócił kod " + str(result.returncode))
        return False
    importlib.invalidate_caches()
    return True


def _tui_available() -> bool:
    """TUI is optional; diagnostic bootstrap also works without this package."""
    if not _interactive():
        return False
    try:
        from prompt_toolkit.shortcuts import radiolist_dialog, button_dialog
        return callable(radiolist_dialog) and callable(button_dialog)
    except (ImportError, AttributeError, ValueError):
        return False


def _ui_mode(requested: str = "auto") -> str:
    if requested == "text":
        return "text"
    if _tui_available():
        return "tui"
    if requested == "tui":
        print("Kursorowy TUI niedostępny: używam tekstowego menu.")
    return "text"


def _choose(ui: str, title: str, description: str, options: list[tuple[str, str]]) -> str | None:
    """Return a stable option key; never perform an install inside the selector."""
    if ui == "tui":
        from prompt_toolkit.shortcuts import radiolist_dialog
        try:
            decision = radiolist_dialog(
                title=title, text=description, values=options,
                ok_text="Wybierz", cancel_text="Wróć",
            ).run()
        except (KeyboardInterrupt, EOFError):
            print("[TUI] Dialog został przerwany. Niczego nie wybrano.")
            return None
        if decision is None:
            print("[TUI] Dialog zamknięty bez wyboru.")
        else:
            print(f"[TUI] Wybrano opcję: {decision}.")
        return decision

    print("\n" + "-" * 56)
    print(title)
    print(description)
    for value, label in options:
        print(f"  [{value}] {label}")
    allowed = {value for value, _ in options}
    while True:
        try:
            selected = input("Wybierz numer (Enter = powrót): ").strip()
        except (KeyboardInterrupt, EOFError):
            return None
        if not selected:
            return None
        if selected in allowed:
            return selected
        print("Wpisz numer jednej z widocznych opcji.")


def _menu(root: Path, report: dict, *, explicit: bool, ui: str = "text") -> bool:
    """One lifecycle-free menu, with numeric and cursor-driven frontends."""
    if not _interactive():
        print("Brak interaktywnego terminala: niczego nie instalowano.")
        return not report["required_issues"]
    while True:
        count = len(report["required_issues"])
        heading = (
            f"GUI: {'GOTOWE' if not count else 'WYMAGA NAPRAWY (' + str(count) + ')'}\n"
            f"Python: {report['interpreter']}\n"
            "Strzałki / Enter / Tab" if ui == "tui" else
            f"GUI: {'GOTOWE' if not count else 'WYMAGA NAPRAWY (' + str(count) + ')'}\n"
            f"Python: {report['interpreter']}\n"
            "Wpisz numer opcji i naciśnij Enter"
        )
        choice = _choose(
            ui, "JAŹŃ | BIBLIOTEKI", heading,
            [("1", "Napraw wymagane biblioteki GUI"),
             ("2", "Wybierz dodatkowy profil do instalacji"),
             ("3", "Wyświetl listę pakietów i wymaganych wersji"),
             ("4", "Odśwież diagnostykę"),
             ("0", "Zakończ" if explicit else "Anuluj start")],
        )
        if choice in (None, "0"):
            print("Diagnostyka zakończona, bez dodatkowej instalacji.")
            return not report["required_issues"] if explicit else False
        if choice == "3":
            show(report, full=True)
            continue
        if choice == "4":
            report = inspect(root)
            show(report, full=False)
            continue
        if choice == "1":
            selected = list(ESSENTIAL)
        elif choice == "2":
            candidates = [(name, rows) for name, rows in report["profiles"].items()
                          if name not in ESSENTIAL]
            options = [
                (str(i), f"{PROFILE_LABELS.get(name, name)} ({name})"
                 f"  {sum(row['state'] == 'PASS' for row in rows)}/{len(rows)} OK")
                for i, (name, rows) in enumerate(candidates, 1)
            ]
            opt = _choose(
                ui, "JAŹŃ | FUNKCJE DODATKOWE",
                "Zaznacz funkcję. Brak pakietu opcjonalnego nie blokuje GUI.",
                options + [("0", "Powrót")],
            )
            if opt in (None, "0"):
                continue
            selected = [candidates[int(opt) - 1][0]]
        else:
            continue

        success = (_install(root, selected, ui="tui") if ui == "tui"
                   else _install(root, selected))
        if not success:
            print("Instalacja anulowana lub nieudana.")
            continue
        report = inspect(root)
        show(report, full=False)
        outstanding = [row for name in selected for row in report["profiles"].get(name, [])
                       if row["state"] != "PASS"]
        if outstanding:
            print(f"[WYMAGA NAPRAWY] {', '.join(selected)}: {len(outstanding)} problemów.")
        else:
            print(f"[GOTOWE] Zainstalowany profil: {', '.join(selected)}.")
        if not explicit and not report["required_issues"]:
            print("Uruchamiam Serce Systemu.")
            return True

def dispatch(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    explicit = "--dependencies" in args
    requested_ui = "auto"
    if explicit:
        args.remove("--dependencies")
        for index, value in enumerate(list(args)):
            if value == "--ui":
                if index + 1 >= len(args):
                    print("Oczekiwano --ui auto, text albo tui.", file=sys.stderr)
                    return 2
                requested_ui = args[index + 1]
                del args[index:index + 2]
                break
            if value.startswith("--ui="):
                requested_ui = value.split("=", 1)[1]
                args.remove(value)
                break
        if requested_ui not in {"auto", "text", "tui"}:
            print("Dozwolone: --ui auto, text, tui.", file=sys.stderr)
            return 2
        if args and (len(args) != 2 or args[0] != "--root"):
            print("Z --dependencies używaj --ui MODE i ewentualnie --root PATH.", file=sys.stderr)
            return 2
    if not explicit and any(value in HELP for value in args):
        from .app import main
        return main(args)
    root = _root(args)
    try:
        report = inspect(root)
        show(report, full=False)
    except (OSError, ValueError, RuntimeError, KeyError) as exc:
        print("Nie można sprawdzić profili: " + type(exc).__name__ + ": " + str(exc),
              file=sys.stderr)
        return 2
    if explicit:
        _menu(root, report, explicit=True, ui=_ui_mode(requested_ui))
        return 0 if not inspect(root)["required_issues"] else 2
    if report["required_issues"] and not _menu(root, report, explicit=False, ui=_ui_mode()):
        print("Brak gotowości zależności GUI. Studio nie zostanie uruchomione.", file=sys.stderr)
        return 2
    # Control plane remains unchanged; bootstrap does not own runtime lifecycle.
    from .app import main
    return main(args)
