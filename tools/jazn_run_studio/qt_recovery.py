"""Opt-in, terminal-only recovery for missing Qt GUI dependencies.

No code in this module starts/stops the Jaźń runtime or accesses MEMORY.
The only install target is the invoking interpreter's existing virtualenv.
"""
from __future__ import annotations

import importlib
import os
from pathlib import Path
import subprocess
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
REQUIREMENTS = Path("tools/jazn_run_studio/requirements.txt")
PYPI_INDEX = "https://pypi.org/simple"


def _interactive() -> bool:
    return bool(sys.stdin and sys.stdout and sys.stdin.isatty() and sys.stdout.isatty())


def _virtualenv() -> bool:
    return sys.prefix != sys.base_prefix


def _install_command() -> list[str]:
    return [
        sys.executable, "-m", "pip", "--isolated", "--require-virtualenv",
        "install", "--index-url", PYPI_INDEX, "--only-binary=:all:",
        "--no-input", "-r", str(REQUIREMENTS),
    ]


def offer_qt_install(error: ImportError, *, allow_install: bool) -> bool:
    """Return True only if the operator approved and Qt re-import succeeded.

    Only a missing PySide6 module enters the menu. Other import or DLL errors
    remain ordinary failures; an unknown dependency is never pip-installed.
    """
    if not isinstance(error, ModuleNotFoundError):
        return False
    if (error.name or "").split(".", 1)[0] != "PySide6":
        return False

    print("\n[Jaźń — Serce Systemu] Brak modułu GUI PySide6.", file=sys.stderr)
    print("Profil: run-studio (wersje z pyproject.toml).")
    print("Źródło online: " + PYPI_INDEX)
    print("Dokumentacja: https://doc.qt.io/qtforpython-6/gettingstarted.html")
    print("Alternatywa offline: zweryfikowany wheelhouse w Studiu Zależności.")

    if not allow_install or getattr(sys, "frozen", False) or not _interactive():
        print("Instalacja wymaga interaktywnego terminala i osobnej zgody.")
        print("Polecenie ręczne w venv, z katalogu repozytorium:")
        print("  python -m pip install -r tools/jazn_run_studio/requirements.txt")
        return False

    while True:
        print("\n  [1] Zainstaluj brakujące zależności GUI z PyPI (w istniejącym venv)")
        print("  [2] Pokaż polecenie instalacji")
        print("  [0] Anuluj (nic nie zmieniaj)")
        try:
            choice = input("Wybór [0/1/2]: ").strip()
        except (EOFError, KeyboardInterrupt):
            return False
        if choice in ("0", ""):
            return False
        if choice == "2":
            print("  " + " ".join(_install_command()))
            continue
        if choice != "1":
            print("Nieznana opcja.")
            continue

        if not _virtualenv():
            print("Odmowa: aktywny Python nie jest środowiskiem wirtualnym.")
            print("Utwórz venv i uruchom Studio jego interpreterem, np.:")
            print("  py -m venv .venv")
            print("  .\\.venv\\Scripts\\python.exe -X utf8 run_studio.py")
            return False
        req = PROJECT_ROOT / REQUIREMENTS
        project = PROJECT_ROOT / "pyproject.toml"
        if not req.is_file() or req.is_symlink() or not project.is_file() or project.is_symlink():
            print("Odmowa: brak kanonicznego profilu zależności w repozytorium.")
            return False
        try:
            profile_lines = [
                line.strip() for line in req.read_text(encoding="utf-8").splitlines()
                if line.strip() and not line.lstrip().startswith("#")
            ]
        except (OSError, UnicodeError):
            return False
        if profile_lines != [".[run-studio]"]:
            print("Odmowa: nieoczekiwany zapis profilu run-studio.")
            return False

        print("\nCel: " + sys.executable)
        print("Instalacja: tylko pakiety binarne, PyPI HTTPS; zgodnie z profilem run-studio.")
        print("UWAGA: pip może zmienić pakiety w tym venv. Nie modyfikuje MEMORY ani daemona.")
        try:
            approved = input("Wpisz TAK, aby wykonać instalację: ").strip()
        except (EOFError, KeyboardInterrupt):
            return False
        if approved.casefold() != "tak":
            print("Anulowano.")
            return False

        pip_env = {key: value for key, value in os.environ.items() if not key.startswith("PIP_")}
        pip_env["PIP_CONFIG_FILE"] = os.devnull
        try:
            result = subprocess.run(
                _install_command(), cwd=PROJECT_ROOT, shell=False, env=pip_env,
                timeout=600, check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            print("Instalacja nie powiodła się: " + type(exc).__name__, file=sys.stderr)
            return False
        if result.returncode != 0:
            print("pip zakończył się kodem " + str(result.returncode), file=sys.stderr)
            return False
        importlib.invalidate_caches()
        try:
            importlib.import_module("PySide6.QtWidgets")
        except ImportError as exc:
            print("Import Qt nadal niesprawny: " + str(exc), file=sys.stderr)
            return False
        print("Qt działa. Uruchamiam interfejs Studio.")
        return True
