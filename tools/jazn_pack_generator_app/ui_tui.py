from __future__ import annotations

import json
import os
import sys
from typing import Any, Callable

from latka_jazn.tools.application_shell import DiagnosticsHub

from .constants import GENERATOR_TITLE, GENERATOR_VERSION
from .service import config_report
from .settings import load_settings
from .ui_text import run_pack_form, run_settings_form, run_unpack_form, run_verify_form


PAGES = ("GŁÓWNA", "OPERACJE", "USTAWIENIA", "DIAGNOSTYKA")
OPERATIONS: tuple[tuple[str, Callable[[], Any]], ...] = (
    ("Pakowanie SYSTEM / MEMORY", run_pack_form),
    ("Rozpakowanie paczki", run_unpack_form),
    ("Weryfikacja paczki", run_verify_form),
    ("Edytuj ustawienia", run_settings_form),
    ("Konfiguracja techniczna", config_report),
)


def _clear() -> None:
    os.system("cls" if os.name == "nt" else "clear")


def _read_key() -> str:
    if os.name == "nt":
        import msvcrt
        ch = msvcrt.getwch()
        if ch in {"\x00", "\xe0"}:
            code = msvcrt.getwch()
            return {"H": "UP", "P": "DOWN", "K": "LEFT", "M": "RIGHT"}.get(code, code)
        if ch in {"\r", "\n"}:
            return "ENTER"
        if ch == "\x1b":
            return "ESC"
        if ch == "\x03":
            return "CTRL_C"
        return ch
    import termios
    import tty
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
        if ch == "\x03": return "CTRL_C"
        if ch == "\x1b":
            seq = sys.stdin.read(2)
            return {"[A": "UP", "[B": "DOWN", "[D": "LEFT", "[C": "RIGHT"}.get(seq, "ESC")
        if ch in {"\r", "\n"}: return "ENTER"
        return ch
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def _fit(text: str, width: int) -> str:
    return text.replace("\t", "    ")[:width].ljust(width)


def _box_line(text: str, width: int = 112) -> str:
    return "║ " + _fit(text, width - 4) + " ║"


def _render(page: int, selected: int, status: str, last_result: str, diagnostics: DiagnosticsHub | None) -> None:
    width = 112
    _clear()
    print("╔" + "═" * (width - 2) + "╗")
    print(_box_line(f"{GENERATOR_TITLE} v{GENERATOR_VERSION}", width))
    tabs = "   ".join(f"[{'●' if idx == page else ' '}] {name}" for idx, name in enumerate(PAGES))
    print(_box_line(tabs, width))
    print("╠" + "═" * (width - 2) + "╣")
    if page == 0:
        settings = load_settings(); cfg = config_report()
        lines = ["STRONA GŁÓWNA", "", "Kanoniczne pakowanie SYSTEM/MEMORY, integralność SHA-256/CRC i bezpieczne rozpakowanie.", "Wszystkie trzy interfejsy korzystają z tego samego rdzenia operacji.", "", f"Domyślny interfejs: {settings.get('ui_mode')}   |   kompresja: {settings.get('compression_level')}   |   część: {settings.get('part_size_mib')} MiB", f"Diagnostyka: {'ON' if settings.get('diagnostics_enabled', True) else 'OFF'}   |   log level: {settings.get('log_level', 'INFO')}", "", f"Platforma: {cfg.get('platform')}   Python: {str(cfg.get('python', '')).splitlines()[0]}", "Przejdź do OPERACJE strzałką → albo klawiszem 2."]
    elif page == 1:
        lines = ["OPERACJE", ""]
        for idx, (label, _) in enumerate(OPERATIONS): lines.append(f"{'▶' if idx == selected else ' '} {idx + 1}. {label}")
        lines += ["", "↑/↓ lub j/k — wybór   Enter — uruchom", "", "Ostatni wynik:", *last_result.splitlines()[-14:]]
    elif page == 2:
        lines = ["USTAWIENIA", "", *json.dumps(load_settings(), ensure_ascii=False, indent=2, default=str).splitlines(), "", "Naciśnij E, aby otworzyć edytor ustawień w terminalu."]
    else:
        lines = ["DIAGNOSTYKA / LOG", ""]
        if diagnostics is None: lines.append("Diagnostyka nie została podłączona do tej sesji.")
        else: lines += [f"Plik: {diagnostics.log_path}", "", *diagnostics.text(limit=25).splitlines()]
    usable = 26
    for line in lines[:usable]: print(_box_line(line, width))
    for _ in range(max(0, usable - len(lines))): print(_box_line("", width))
    print("╠" + "═" * (width - 2) + "╣")
    print(_box_line(f"{status}   |   1-4 strony • ←/→ zmiana • q/Ctrl+C wyjście", width))
    print("╚" + "═" * (width - 2) + "╝")


def _run_operation(index: int, diagnostics: DiagnosticsHub | None) -> tuple[str, str]:
    label, action = OPERATIONS[index]
    _clear(); print(f"{GENERATOR_TITLE} — {label}\n{'=' * 72}\n")
    if diagnostics is not None: diagnostics.record("INFO", "Uruchomiono operację TUI", operation=label)
    try:
        result = action(); rendered = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True, default=str)
        print("\nWYNIK\n" + rendered)
        if diagnostics is not None: diagnostics.record("INFO", "Zakończono operację TUI", operation=label)
        input("\nEnter — powrót do TUI..."); return f"Zakończono: {label}", rendered
    except KeyboardInterrupt:
        if diagnostics is not None: diagnostics.record("WARNING", "Przerwano operację TUI", operation=label)
        return f"Przerwano: {label}", "Operacja przerwana przez użytkownika."
    except Exception as exc:
        if diagnostics is not None: diagnostics.exception(exc, context=f"Błąd operacji TUI: {label}")
        rendered = f"{type(exc).__name__}: {exc}"; print("\nBŁĄD: " + rendered); input("\nEnter — powrót do TUI...")
        return f"Błąd: {label}", rendered


def run_terminal_tui(diagnostics: DiagnosticsHub | None = None) -> int:
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        from .ui_text import run_text_ui
        return run_text_ui(diagnostics)
    page = 0; selected = 0; status = "Gotowe"; last_result = "Brak wyników w tej sesji."
    if diagnostics is not None: diagnostics.record("INFO", "Uruchomiono terminalowy TUI")
    while True:
        _render(page, selected, status, last_result, diagnostics)
        key = _read_key()
        if key in {"CTRL_C", "ESC", "q", "Q"}:
            if diagnostics is not None: diagnostics.record("INFO", "Zamknięto terminalowy TUI")
            return 0 if key != "CTRL_C" else 130
        if key in {"1", "2", "3", "4"}: page = int(key) - 1; continue
        if key == "RIGHT": page = (page + 1) % len(PAGES); continue
        if key == "LEFT": page = (page - 1) % len(PAGES); continue
        if page == 1 and key in {"DOWN", "j", "J"}: selected = (selected + 1) % len(OPERATIONS)
        elif page == 1 and key in {"UP", "k", "K"}: selected = (selected - 1) % len(OPERATIONS)
        elif page == 1 and key == "ENTER": status, last_result = _run_operation(selected, diagnostics)
        elif page == 2 and key in {"e", "E", "ENTER"}: status, last_result = _run_operation(3, diagnostics)
