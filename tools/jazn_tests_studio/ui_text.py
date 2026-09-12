from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

from latka_jazn.tools.application_shell import DiagnosticsHub

from .core import (
    APP_NAME,
    APP_VERSION,
    audit,
    effective_contract,
    filtered,
    load_ui_settings,
    save_ui_settings,
    set_review,
)
from .runner import run_pytest


def print_home(root: Path) -> None:
    data = audit(root)
    print(f"{APP_NAME} {APP_VERSION}")
    print(f"Repo: {data['root']}")
    print(f"Aktywne definicje: {data['definitions']} | ręczne recenzje: {data['manual_reviews']}")
    print("Statusy:", data["by_status"])
    print("Kategorie:", data["by_category"])
    print(f"Katalog wczytany w: {data['catalog_load_seconds']:.4f}s")
    print("\ncurrent = aktywny kontrakt techniczny; sens może wymagać recenzji.")


def _settings(root: Path) -> None:
    settings = load_ui_settings(root)
    while True:
        print("\nUSTAWIENIA")
        print(f"1. Domyślny interfejs: {settings.ui_mode}")
        print(f"2. Splashscreen: {'włączony' if settings.splash_enabled else 'wyłączony'}")
        print(f"3. Diagnostyka/log: {'włączona' if settings.diagnostics_enabled else 'wyłączona'}")
        print(f"4. Poziom logów: {settings.log_level}")
        print("0. Powrót")
        raw = input("ustawienia> ").strip().lower()
        if raw in {"0", "q", "back"}:
            return
        if raw == "1":
            mode = input("text/tui/window: ").strip().lower()
            if mode in {"text", "tui", "window"}:
                settings = replace(settings, ui_mode=mode)
        elif raw == "2":
            settings = replace(settings, splash_enabled=not settings.splash_enabled)
        elif raw == "3":
            settings = replace(settings, diagnostics_enabled=not settings.diagnostics_enabled)
        elif raw == "4":
            level = input("DEBUG/INFO/WARNING/ERROR: ").strip().upper()
            if level in {"DEBUG", "INFO", "WARNING", "ERROR"}:
                settings = replace(settings, log_level=level)
        settings = save_ui_settings(root, settings)
        print("Zapisano.")


def run_text_ui(root: Path, diagnostics: DiagnosticsHub) -> int:
    print_home(root)
    print(
        "\nPolecenia: home, list [tekst], show <nodeid>, run <nodeid>, run-all, audit, "
        "review <nodeid> <status>, settings, diagnostics, quit"
    )
    while True:
        try:
            raw = input("tests-studio> ").strip()
        except EOFError:
            return 0
        if not raw:
            continue
        if raw in {"quit", "exit", "q"}:
            diagnostics.record("INFO", "Zamknięto interfejs tekstowy")
            return 0
        if raw == "home":
            print_home(root)
            continue
        if raw == "settings":
            _settings(root)
            updated = load_ui_settings(root)
            diagnostics.reconfigure(
                enabled=updated.diagnostics_enabled,
                limit=updated.diagnostics_limit,
                minimum_level=updated.log_level,
            )
            continue
        if raw == "diagnostics":
            print(f"Log: {diagnostics.log_path}")
            print(diagnostics.text(limit=100))
            continue
        if raw == "audit":
            payload = audit(root)
            diagnostics.record("INFO", "Wykonano audyt katalogu testów", definitions=payload.get("definitions"))
            print(json.dumps(payload, indent=2, ensure_ascii=False))
            continue
        if raw == "run-all":
            diagnostics.record("INFO", "Uruchamiam cały aktywny zestaw testów")
            result = run_pytest(root, live=True, on_event=lambda event: diagnostics.record("DEBUG", "pytest", event=event.get("type")))
            diagnostics.record("INFO" if result.get("ok") else "ERROR", "Zakończono cały zestaw testów", result=result)
            print(json.dumps(result, indent=2, ensure_ascii=False))
            continue
        if raw.startswith("list"):
            query = raw[4:].strip()
            for nodeid, item in filtered(root, query)[:200]:
                print(f"[{item.get('status', 'current')}] {nodeid} — {item.get('purpose', '')}")
            continue
        if raw.startswith("show "):
            nodeid = raw[5:].strip()
            try:
                print(json.dumps(effective_contract(root, nodeid), indent=2, ensure_ascii=False))
            except KeyError:
                print("Nieznany nodeid")
            continue
        if raw.startswith("run "):
            nodeid = raw[4:].strip()
            diagnostics.record("INFO", "Uruchamiam pojedynczy test", nodeid=nodeid)
            result = run_pytest(root, [nodeid], live=True)
            diagnostics.record("INFO" if result.get("ok") else "ERROR", "Zakończono pojedynczy test", nodeid=nodeid, result=result)
            print(json.dumps(result, indent=2, ensure_ascii=False))
            continue
        if raw.startswith("review "):
            parts = raw.split(maxsplit=2)
            if len(parts) == 3:
                set_review(root, parts[1], parts[2])
                diagnostics.record("INFO", "Zapisano recenzję testu", nodeid=parts[1], status=parts[2])
                print("Zapisano.")
            continue
        print("Nieznane polecenie.")
