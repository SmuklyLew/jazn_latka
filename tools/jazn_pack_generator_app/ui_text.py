from __future__ import annotations

import json
from pathlib import Path
from threading import Event
from typing import Any

from .constants import DEFAULT_COMPRESSION_LEVEL, DEFAULT_PART_SIZE_MIB, GENERATOR_TITLE, GENERATOR_VERSION
from .models import ContentMode, PackRequest, ProgressEvent, TransportMode
from .service import config_report, pack, plan_pack, unpack_package, verify_package
from .settings import load_settings, save_settings


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


def _choice(prompt: str, values: tuple[str, ...], default: str) -> str:
    print(prompt)
    for index, value in enumerate(values, start=1):
        marker = "*" if value == default else " "
        print(f" {marker} {index}. {value}")
    raw = _ask("Wybór", str(values.index(default) + 1))
    if raw.isdigit() and 1 <= int(raw) <= len(values):
        return values[int(raw) - 1]
    return raw if raw in values else default


def _progress(event: ProgressEvent) -> None:
    if event.total > 0:
        percent = int(event.fraction * 100)
        path = f" — {event.path}" if event.path else ""
        print(f"\r[{percent:3d}%] {event.message}{path}"[:160].ljust(160), end="", flush=True)
    else:
        print(f"\r{event.message}".ljust(160), end="", flush=True)


def _default_output(source: Path, settings: dict[str, Any]) -> Path:
    configured = str(settings.get("output_root") or "").strip()
    if configured:
        return Path(configured).expanduser()
    return source.parent / "jazn_packages"


def run_pack_form() -> dict[str, Any]:
    settings = load_settings()
    source = Path(_ask("Folder Jaźni", str(settings.get("source_root") or Path.cwd()))).expanduser()
    output = Path(_ask("Folder wynikowy", str(_default_output(source, settings)))).expanduser()
    content = ContentMode(_choice("Co spakować?", ("system", "memory", "system+memory"), "system"))
    memory: Path | None = None
    if content in {ContentMode.MEMORY, ContentMode.SYSTEM_AND_MEMORY}:
        raw_memory = _ask("Folder pamięci (puste = auto/JAZN_MEMORY_ROOT)", str(settings.get("memory_root") or ""))
        memory = Path(raw_memory).expanduser() if raw_memory else None
    split = _yes_no("Podzielić duży ZIP na części transportowe?", False)
    part_size = int(_ask("Rozmiar części MiB", str(settings.get("part_size_mib") or DEFAULT_PART_SIZE_MIB))) if split else DEFAULT_PART_SIZE_MIB
    compression = int(_ask("Poziom kompresji ZIP 0..9", str(settings.get("compression_level") or DEFAULT_COMPRESSION_LEVEL)))
    request = PackRequest(
        source_root=source,
        output_root=output,
        content=content,
        memory_root=memory,
        transport=TransportMode.SPLIT if split else TransportMode.SINGLE,
        part_size_mib=part_size,
        compression_level=compression,
    )
    plan = plan_pack(request)
    print("\nPLAN")
    print(json.dumps(plan.summary(), ensure_ascii=False, indent=2))
    if not _yes_no("Uruchomić pakowanie?", False):
        return {"ok": False, "cancelled": True}
    result = pack(request, callback=_progress, cancel_event=Event())
    print()
    if bool(settings.get("remember_last_paths", True)):
        settings.update(
            {
                "source_root": str(source.resolve()),
                "memory_root": str(memory.resolve()) if memory else "",
                "output_root": str(output.resolve()),
                "part_size_mib": part_size,
                "compression_level": compression,
            }
        )
        save_settings(settings)
    return result.to_dict()


def run_verify_form() -> dict[str, Any]:
    path = Path(_ask("ZIP albo pierwsza część .zip.001")).expanduser()
    result = verify_package(path, callback=_progress)
    print()
    return result


def run_unpack_form() -> dict[str, Any]:
    path = Path(_ask("ZIP albo pierwsza część .zip.001")).expanduser()
    destination = Path(_ask("Katalog docelowy", str(Path.cwd() / "jazn_unpacked"))).expanduser()
    overwrite = _yes_no("Zastąpić istniejący katalog docelowy?", False)
    result = unpack_package(path, destination, overwrite=overwrite, callback=_progress)
    print()
    return {"ok": True, "destination": str(result)}


def run_settings_form() -> dict[str, Any]:
    settings = load_settings()
    settings["ui_mode"] = _choice("Domyślny interfejs", ("text", "tui", "studio"), str(settings["ui_mode"]))
    settings["output_root"] = _ask("Domyślny folder wynikowy", str(settings.get("output_root") or ""))
    settings["part_size_mib"] = int(_ask("Domyślny rozmiar części MiB", str(settings["part_size_mib"])))
    settings["compression_level"] = int(_ask("Domyślny poziom kompresji 0..9", str(settings["compression_level"])))
    settings["remember_last_paths"] = _yes_no("Zapamiętywać ostatnie ścieżki?", bool(settings["remember_last_paths"]))
    return save_settings(settings)


def run_text_ui() -> int:
    while True:
        print(f"\n{GENERATOR_TITLE} v{GENERATOR_VERSION}")
        print("=" * 72)
        print("1. Pakowanie")
        print("2. Rozpakowywanie")
        print("3. Weryfikacja paczki")
        print("4. Ustawienia")
        print("5. Konfiguracja")
        print("0. Wyjście")
        command = input("\nWybór: ").strip()
        try:
            if command == "1":
                result = run_pack_form()
            elif command == "2":
                result = run_unpack_form()
            elif command == "3":
                result = run_verify_form()
            elif command == "4":
                result = run_settings_form()
            elif command == "5":
                result = config_report()
            elif command == "0":
                return 0
            else:
                continue
            print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        except Exception as exc:
            print(f"\nBŁĄD: {type(exc).__name__}: {exc}")
        input("\nEnter — powrót...")
