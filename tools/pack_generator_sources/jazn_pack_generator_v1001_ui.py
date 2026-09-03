from __future__ import annotations

import json
import os
from pathlib import Path
import sys
from typing import Any, Sequence

UI_MODE_CHOICES = ("tekstowy", "kursorowy", "studio-terminal")
UI_MODE_LABELS = {
    "tekstowy": "Podstawowy tryb tekstowy",
    "kursorowy": "Podstawowy tryb kursorowy",
    "studio-terminal": "Jaźń Pack Studio w terminalu",
}

_CORE: Any = None


def bind(core: Any) -> None:
    global _CORE
    _CORE = core


def _core() -> Any:
    if _CORE is None:
        raise RuntimeError("Jaźń Pack Generator v10.0.1 UI is not bound")
    return _CORE


def _clear() -> None:
    if sys.stdout.isatty():
        os.system("cls" if os.name == "nt" else "clear")


def _ask(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    value = input(f"{prompt}{suffix}: ").strip()
    return value or default


def _yes_no(prompt: str, default: bool = False) -> bool:
    marker = "T/n" if default else "t/N"
    value = input(f"{prompt} [{marker}]: ").strip().casefold()
    if not value:
        return default
    return value in {"t", "tak", "y", "yes", "1", "true"}


def _choice(prompt: str, choices: Sequence[str], default: str) -> str:
    print(prompt)
    for idx, choice in enumerate(choices, start=1):
        mark = "*" if choice == default else " "
        print(f" {mark} {idx}. {choice}")
    raw = _ask("Wybór", str(list(choices).index(default) + 1))
    if raw.isdigit() and 1 <= int(raw) <= len(choices):
        return choices[int(raw) - 1]
    if raw in choices:
        return raw
    return default


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
        if ch == "\t":
            return "TAB"
        return ch
    if not sys.stdin.isatty():
        return input().strip()
    import termios
    import tty

    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
        if ch == "\x1b":
            seq = sys.stdin.read(2)
            return {"[A": "UP", "[B": "DOWN", "[C": "RIGHT", "[D": "LEFT"}.get(seq, "ESC")
        if ch in {"\r", "\n"}:
            return "ENTER"
        if ch == "\t":
            return "TAB"
        return ch
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def _cursor_select(title: str, options: Sequence[str], *, initial: int = 0) -> int:
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raw = _choice(title, options, options[initial])
        return list(options).index(raw)
    index = max(0, min(initial, len(options) - 1))
    while True:
        _clear()
        print(title)
        print("─" * max(40, len(title)))
        for idx, option in enumerate(options):
            print(("› " if idx == index else "  ") + option)
        print("\n↑↓ wybór   Enter otwórz   Esc wróć")
        key = _read_key()
        if key == "UP":
            index = (index - 1) % len(options)
        elif key == "DOWN":
            index = (index + 1) % len(options)
        elif key == "ENTER":
            return index
        elif key in {"ESC", "q", "Q"}:
            return -1


def _settings() -> dict[str, Any]:
    return _core().load_settings()


def _save(settings: dict[str, Any]) -> dict[str, Any]:
    return _core().save_settings(**settings)


def _pack_form(settings: dict[str, Any]) -> dict[str, Any]:
    core = _core()
    print("\nPAKOWANIE")
    print("═" * 72)
    settings["source"] = _ask("Źródło systemu Jaźni", str(settings["source"]))
    settings["out_dir"] = _ask("Folder wynikowy (poza repo)", str(settings["out_dir"]))
    settings["content"] = _choice("Co spakować?", core.CONTENT_CHOICES, str(settings["content"]))
    if settings["content"] == "system+memory":
        settings["layout"] = _choice(
            "SYSTEM + PAMIĘĆ:", core.LAYOUT_CHOICES, str(settings.get("layout") or "single")
        )
    else:
        settings["layout"] = "single"
    settings["archive_format"] = _choice(
        "Format paczki/transportu:", core.ARCHIVE_FORMAT_CHOICES, str(settings["archive_format"])
    )
    if settings["archive_format"] == "split-zip":
        settings["split_size_mib"] = int(_ask("Rozmiar części MiB", str(settings["split_size_mib"])))
    if settings["content"] in {"system", "system+memory"}:
        settings["target_alias"] = _choice(
            "Platforma zależności:", core.DISTRIBUTION_TARGET_CHOICES, str(settings["target_alias"])
        )
        settings["python_version"] = _choice(
            "Python:", core.DISTRIBUTION_PYTHON_CHOICES, str(settings["python_version"])
        )
        settings["dependency_bundle"] = _ask(
            "Zweryfikowany dependency bundle (puste = auto)", str(settings.get("dependency_bundle") or "")
        )
        settings["materialize_dependencies"] = _yes_no(
            "Pobrać/materializować zależności natywnie, jeśli bundle nie istnieje?",
            bool(settings.get("materialize_dependencies")),
        )
    _save(settings)
    plan = core.distribution_request_plan(
        content=settings["content"], layout=settings["layout"], archive_format=settings["archive_format"]
    )
    print("\nPLAN")
    print(json.dumps(plan, ensure_ascii=False, indent=2))
    if not _yes_no("Uruchomić pakowanie?", False):
        return {"ok": False, "cancelled": True}
    return core.run_pack_request(
        source=settings["source"],
        out_dir=settings["out_dir"],
        content=settings["content"],
        layout=settings["layout"],
        archive_format=settings["archive_format"],
        split_size_mib=int(settings["split_size_mib"]),
        target_alias=settings["target_alias"],
        python_version=settings["python_version"],
        dependency_bundle=str(settings.get("dependency_bundle") or "") or None,
        materialize_dependencies=bool(settings.get("materialize_dependencies")),
    )


def _unpack_form(settings: dict[str, Any]) -> dict[str, Any]:
    core = _core()
    print("\nROZPAKOWYWANIE")
    print("═" * 72)
    archive = _ask("Archiwum / pierwsza część .zip.001")
    if not archive:
        return {"ok": False, "cancelled": True}
    info = core.inspect_archive(archive)
    print(json.dumps(info, ensure_ascii=False, indent=2))
    destination = _ask("Katalog docelowy", str(Path.cwd() / "unpacked"))
    if not _yes_no("Rozpakować po poprawnym preflight?", False):
        return info
    return core.unpack_archive(archive, destination)


def _settings_form(settings: dict[str, Any]) -> dict[str, Any]:
    core = _core()
    print("\nUSTAWIENIA")
    print("═" * 72)
    settings["ui_mode"] = _choice("Domyślny interfejs", UI_MODE_CHOICES, str(settings["ui_mode"]))
    settings["out_dir"] = _ask("Domyślny folder wynikowy", str(settings["out_dir"]))
    settings["archive_format"] = _choice(
        "Domyślny format", core.ARCHIVE_FORMAT_CHOICES, str(settings["archive_format"])
    )
    settings["split_size_mib"] = int(_ask("Domyślny rozmiar części MiB", str(settings["split_size_mib"])))
    return _save(settings)


def _config_view() -> dict[str, Any]:
    payload = _core().config_report()
    print("\nKONFIGURACJA")
    print("═" * 72)
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return payload


def run_text_ui() -> int:
    settings = _settings()
    while True:
        _clear()
        print(f"Jaźń Pack Generator v{_core().GENERATOR_VERSION}")
        print(_core().GENERATOR_TITLE)
        print("=" * 72)
        print("1. PAKOWANIE")
        print("2. ROZPAKOWYWANIE")
        print("3. USTAWIENIA")
        print("4. KONFIGURACJA")
        print("0. WYJŚCIE")
        command = input("\nWybór: ").strip()
        try:
            if command == "1":
                result = _pack_form(settings)
            elif command == "2":
                result = _unpack_form(settings)
            elif command == "3":
                settings = _settings_form(settings)
                result = settings
            elif command == "4":
                result = _config_view()
            elif command == "0":
                return 0
            else:
                continue
            print("\nWYNIK")
            print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        except Exception as exc:
            print(f"\nBŁĄD: {type(exc).__name__}: {exc}")
        input("\nEnter — powrót...")


def run_cursor_ui() -> int:
    settings = _settings()
    labels = ("PAKOWANIE", "ROZPAKOWYWANIE", "USTAWIENIA", "KONFIGURACJA", "WYJŚCIE")
    while True:
        selected = _cursor_select(
            f"Jaźń Pack Generator v{_core().GENERATOR_VERSION} — tryb kursorowy", labels
        )
        if selected < 0 or selected == 4:
            return 0
        _clear()
        try:
            if selected == 0:
                result = _pack_form(settings)
            elif selected == 1:
                result = _unpack_form(settings)
            elif selected == 2:
                settings = _settings_form(settings)
                result = settings
            else:
                result = _config_view()
            print("\nWYNIK")
            print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        except Exception as exc:
            print(f"\nBŁĄD: {type(exc).__name__}: {exc}")
        input("\nEnter — powrót...")


def _studio_dashboard(settings: dict[str, Any], page: int) -> None:
    core = _core()
    pages = ("PAKOWANIE", "ROZPAKOWYWANIE", "USTAWIENIA", "KONFIGURACJA")
    width = 96
    _clear()
    print("╔" + "═" * (width - 2) + "╗")
    title = f" Jaźń Pack Studio v{core.GENERATOR_VERSION} — {core.GENERATOR_TITLE} "
    print("║" + title[: width - 2].ljust(width - 2) + "║")
    print("╠" + "═" * (width - 2) + "╣")
    tab_line = "  ".join(
        (f"[ {name} ]" if idx == page else f"  {name}  ") for idx, name in enumerate(pages)
    )
    print("║" + tab_line[: width - 2].ljust(width - 2) + "║")
    print("╠" + "═" * (width - 2) + "╣")
    if page == 0:
        left = [
            "ZAWARTOŚĆ", f"  {settings['content']}", "", "UKŁAD", f"  {settings['layout']}",
            "", "FORMAT", f"  {settings['archive_format']}",
        ]
        right = [
            "Źródło:", f"  {settings['source']}", "Folder wynikowy:", f"  {settings['out_dir']}",
            "Target / Python:", f"  {settings['target_alias']} / {settings['python_version']}",
            "Zależności SYSTEMU:", "  core + archive / zweryfikowany wheelhouse",
            "Pamięć:", "  kanoniczny exporter package_distribution",
        ]
    elif page == 1:
        left = ["ROZPAKOWYWANIE", "", "ZIP / split ZIP", "7z", "TAR", "RAR"]
        right = [
            "Najpierw wykonywany jest preflight:", "  • walidacja ścieżek", "  • test integralności/CRC",
            "  • staging", "  • dopiero potem commit katalogu docelowego",
        ]
    elif page == 2:
        left = ["USTAWIENIA", "", f"UI: {settings['ui_mode']}", f"Split: {settings['split_size_mib']} MiB"]
        right = [
            "Domyślny output:", f"  {settings['out_dir']}", "Generator nie zapisuje paczek do repo.",
            "local_private_canon_extension.py jest twardo wykluczony z SYSTEMU.",
        ]
    else:
        status = core.archive_backend_status()
        left = ["BACKENDY", "", "ZIP", "split ZIP", "7z", "TAR", "RAR"]
        right = [json.dumps(status, ensure_ascii=False, indent=2)]
    rows = max(len(left), len(right))
    split = 28
    for idx in range(rows):
        left_text = left[idx] if idx < len(left) else ""
        right_text = right[idx] if idx < len(right) else ""
        chunks = right_text.splitlines() or [""]
        print(
            "║ " + left_text[: split - 2].ljust(split - 2) + "│ "
            + chunks[0][: width - split - 4].ljust(width - split - 4) + " ║"
        )
        for chunk in chunks[1:]:
            print(
                "║ " + "".ljust(split - 2) + "│ "
                + chunk[: width - split - 4].ljust(width - split - 4) + " ║"
            )
    print("╠" + "═" * (width - 2) + "╣")
    footer = "Tab/←→ karta   Enter otwórz   P pakuj   U rozpakuj   Q wyjście"
    print("║" + footer[: width - 2].ljust(width - 2) + "║")
    print("╚" + "═" * (width - 2) + "╝")


def run_terminal_studio() -> int:
    settings = _settings()
    page = 0
    while True:
        _studio_dashboard(settings, page)
        key = _read_key()
        if key in {"q", "Q", "ESC"}:
            return 0
        if key in {"TAB", "RIGHT"}:
            page = (page + 1) % 4
            continue
        if key == "LEFT":
            page = (page - 1) % 4
            continue
        try:
            if key in {"p", "P"}:
                _clear()
                result = _pack_form(settings)
            elif key in {"u", "U"}:
                _clear()
                result = _unpack_form(settings)
            elif key == "ENTER":
                _clear()
                if page == 0:
                    result = _pack_form(settings)
                elif page == 1:
                    result = _unpack_form(settings)
                elif page == 2:
                    settings = _settings_form(settings)
                    result = settings
                else:
                    result = _config_view()
            else:
                continue
            print("\nWYNIK")
            print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        except Exception as exc:
            print(f"\nBŁĄD: {type(exc).__name__}: {exc}")
        input("\nEnter — powrót do Studio...")


def run_ui_mode(mode: str, argv: Sequence[str] | None = None) -> int:
    normalized = str(mode).strip().lower()
    if normalized == "tekstowy":
        return run_text_ui()
    if normalized == "kursorowy":
        return run_cursor_ui()
    if normalized == "studio-terminal":
        return run_terminal_studio()
    raise ValueError(f"unsupported UI mode: {mode!r}")


def main(argv: Sequence[str] | None = None) -> int:
    raw = list(sys.argv[1:] if argv is None else argv)
    if raw and raw[0] == "ui":
        if len(raw) < 2:
            raise SystemExit("ui requires one of: " + ", ".join(UI_MODE_CHOICES))
        return run_ui_mode(raw[1], raw[2:])
    if raw:
        return int(_core().main(raw))
    settings = _settings()
    mode = str(settings.get("ui_mode") or "studio-terminal")
    if mode not in UI_MODE_CHOICES:
        mode = "studio-terminal"
    return run_ui_mode(mode)


if __name__ == "__main__":
    raise SystemExit(main())
