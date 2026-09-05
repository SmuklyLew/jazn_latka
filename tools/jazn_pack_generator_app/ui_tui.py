from __future__ import annotations

import os
import sys

from .constants import GENERATOR_TITLE, GENERATOR_VERSION
from .service import config_report
from .ui_text import run_pack_form, run_settings_form, run_unpack_form, run_verify_form


def _clear() -> None:
    os.system("cls" if os.name == "nt" else "clear")


def _read_key() -> str:
    if os.name == "nt":
        import msvcrt
        ch = msvcrt.getwch()
        if ch in {"\x00", "\xe0"}:
            code = msvcrt.getwch()
            return {"H": "UP", "P": "DOWN"}.get(code, code)
        if ch in {"\r", "\n"}:
            return "ENTER"
        if ch == "\x1b":
            return "ESC"
        return ch
    import termios
    import tty
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
        if ch == "\x1b":
            seq = sys.stdin.read(2)
            return {"[A": "UP", "[B": "DOWN"}.get(seq, "ESC")
        if ch in {"\r", "\n"}:
            return "ENTER"
        return ch
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def _draw(index: int) -> None:
    options = (
        "PAKOWANIE",
        "ROZPAKOWYWANIE",
        "WERYFIKACJA",
        "USTAWIENIA",
        "KONFIGURACJA",
        "WYJŚCIE",
    )
    width = 88
    _clear()
    print("╔" + "═" * (width - 2) + "╗")
    title = f" {GENERATOR_TITLE} v{GENERATOR_VERSION} — terminalowy TUI "
    print("║" + title[: width - 2].center(width - 2) + "║")
    print("╠" + "═" * (width - 2) + "╣")
    print("║  Nawigacja: ↑ ↓   Enter — wybór   Esc — wyjście".ljust(width - 1) + "║")
    print("╠" + "═" * (width - 2) + "╣")
    for idx, option in enumerate(options):
        marker = "▶" if idx == index else " "
        line = f"║  {marker}  {option}"
        print(line.ljust(width - 1) + "║")
    print("╠" + "═" * (width - 2) + "╣")
    print("║  SYSTEM / MEMORY / SYSTEM+MEMORY  •  ZIP  •  opcjonalne części transportowe".ljust(width - 1) + "║")
    print("╚" + "═" * (width - 2) + "╝")


def run_terminal_tui() -> int:
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        from .ui_text import run_text_ui
        return run_text_ui()
    index = 0
    while True:
        _draw(index)
        key = _read_key()
        if key == "UP":
            index = (index - 1) % 6
        elif key == "DOWN":
            index = (index + 1) % 6
        elif key in {"ESC", "q", "Q"}:
            return 0
        elif key == "ENTER":
            if index == 5:
                return 0
            _clear()
            try:
                if index == 0:
                    result = run_pack_form()
                elif index == 1:
                    result = run_unpack_form()
                elif index == 2:
                    result = run_verify_form()
                elif index == 3:
                    result = run_settings_form()
                else:
                    result = config_report()
                print("\nWYNIK")
                print(result)
            except Exception as exc:
                print(f"\nBŁĄD: {type(exc).__name__}: {exc}")
            input("\nEnter — powrót do TUI...")
