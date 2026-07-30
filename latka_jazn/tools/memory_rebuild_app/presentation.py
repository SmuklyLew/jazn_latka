from __future__ import annotations

from pathlib import Path
from typing import Any

from .models import BaselineSpec, SourceSpec
from .source_browser import human_size

ROLE_LABELS = {
    "chatgpt_export": "Eksport rozmów ChatGPT",
    "chatgpt_html_export": "HTML rozmów — kontrola",
    "journal": "Dziennik",
    "approved_l0": "Zatwierdzone źródło L0",
    "layered_memory": "Starsza pamięć warstwowa",
    "runtime_event_ledger": "Dziennik zdarzeń runtime",
    "sqlite_snapshot": "Migawka SQLite",
    "reference_document": "Dokument pomocniczy",
    "visual_asset": "Grafika / załącznik",
    "unknown": "Nierozpoznane",
}

PIPELINE_LABELS = {
    "memory_rebuild": "Wejdzie do odbudowy pamięci",
    "html_control": "Tylko kontrola HTML",
    "catalog_only": "Źródło referencyjne — bez bezpośredniego importu",
    "sqlite_baseline": "Baza porównawcza",
    "excluded": "Pominięte",
}

TRUTH_LABELS = {
    "conversation_event": "Zdarzenie rozmowy",
    "source_recorded": "Zapis źródłowy",
    "user_confirmed": "Potwierdzone przez użytkownika",
    "assistant_claim": "Twierdzenie dawnej asystentki",
    "runtime_claim": "Twierdzenie runtime — wymaga weryfikacji",
    "dream": "Sen",
    "imagination": "Wyobraźnia",
    "book_scene": "Scena książkowa",
    "roleplay": "Roleplay",
    "symbolic": "Materiał symboliczny",
    "technical": "Dane techniczne",
    "unknown": "Nierozpoznane",
}

WARNING_LABELS = {
    "blocking:source_missing": "Plik nie istnieje.",
    "blocking:source_not_file": "Podana ścieżka jest folderem, a nie plikiem. Użyj „Przeskanuj folder”.",
    "blocking:zip_unsafe_paths": "ZIP zawiera niebezpieczne ścieżki.",
    "blocking:zip_symlinks": "ZIP zawiera dowiązania symboliczne.",
    "blocking:zip_duplicate_members": "ZIP zawiera duplikaty lub kolizje nazw.",
    "blocking:zip_crc_failed": "Kontrola CRC ZIP nie przeszła.",
    "jsonl_sample_contains_invalid_records": "Próbka JSONL zawiera niepoprawne rekordy.",
}

ERROR_LABELS = {
    "target_root_missing": "Nie ustawiono katalogu docelowego.",
    "enabled_sources_missing": "Co najmniej jeden włączony wpis nie wskazuje na istniejący plik.",
    "enabled_sources_blocked": "Co najmniej jedno źródło jest zablokowane przez kontrolę bezpieczeństwa.",
    "no_memory_rebuild_sources": "Nie ma żadnego źródła przeznaczonego do odbudowy pamięci.",
    "developer_target_inside_repository": "W trybie developer katalog docelowy musi być poza repozytorium.",
}


def _yes(value: bool) -> str:
    return "Tak" if value else "Nie"


def source_title(source: SourceSpec) -> str:
    status = "✓" if source.status == "ready" and not any(item.startswith("blocking:") for item in source.warnings) else "!"
    enabled = "WŁ." if source.enabled else "WYŁ."
    return (
        f"{source.order:02d} [{enabled}] {status} "
        f"{ROLE_LABELS.get(source.role, source.role)} — {Path(source.path).name}"
    )


def format_source(source: SourceSpec) -> str:
    warnings = [WARNING_LABELS.get(item, item) for item in source.warnings]
    metadata = source.metadata or {}
    lines = [
        f"Plik: {Path(source.path).name}",
        f"Folder: {Path(source.path).parent}",
        f"Istnieje: {_yes(Path(source.path).is_file())}",
        f"Włączony: {_yes(source.enabled)}",
        f"Zatwierdzony: {_yes(source.approved)}",
        f"Rola: {ROLE_LABELS.get(source.role, source.role)}",
        f"Użycie: {PIPELINE_LABELS.get(source.pipeline, source.pipeline)}",
        f"Rodzaj treści: {TRUTH_LABELS.get(source.truth_domain, source.truth_domain)}",
        f"Rodzina źródła: {source.source_family or '—'}",
        f"Rozmiar: {human_size(source.size_bytes)}",
        f"SHA-256: {source.sha256 or 'nieobliczone'}",
        f"Stan: {source.status}",
    ]
    if warnings:
        lines.extend(("", "Uwagi:", *(f"  • {item}" for item in warnings)))
    zip_meta = metadata.get("zip") if isinstance(metadata, dict) else None
    if isinstance(zip_meta, dict):
        lines.extend(
            (
                "",
                "ZIP:",
                f"  • plików w archiwum: {zip_meta.get('member_count', 0)}",
                f"  • plików rozmów: {len(zip_meta.get('conversation_members') or [])}",
                f"  • plików HTML: {len(zip_meta.get('html_members') or [])}",
                f"  • grafik: {zip_meta.get('image_member_count', 0)}",
                f"  • CRC sprawdzone: {_yes(bool(zip_meta.get('crc_checked')))}",
            )
        )
    json_meta = metadata.get("json") if isinstance(metadata, dict) else None
    if isinstance(json_meta, dict):
        count = json_meta.get("entry_count", json_meta.get("item_count"))
        if count is not None:
            lines.extend(("", f"Liczba rekordów w JSON: {count}"))
    jsonl_meta = metadata.get("jsonl") if isinstance(metadata, dict) else None
    if isinstance(jsonl_meta, dict):
        lines.extend(
            (
                "",
                "Próbka JSONL:",
                f"  • poprawne rekordy: {jsonl_meta.get('sample_valid_json', 0)}",
                f"  • błędne rekordy: {jsonl_meta.get('sample_invalid_json', 0)}",
            )
        )
    return "\n".join(lines)


def baseline_title(baseline: BaselineSpec) -> str:
    enabled = "WŁ." if baseline.enabled else "WYŁ."
    status = "✓" if baseline.status == "ready" else "!"
    return f"[{enabled}] {status} {baseline.label} — {Path(baseline.path).name}"


def format_baseline(baseline: BaselineSpec) -> str:
    summary = baseline.summary or {}
    databases = summary.get("databases", {}) if isinstance(summary, dict) else {}
    lines = [
        f"Nazwa: {baseline.label}",
        f"Folder: {baseline.path}",
        f"Włączony: {_yes(baseline.enabled)}",
        "Tryb: tylko do odczytu",
        f"Stan: {baseline.status}",
        f"Dostępne bazy: {summary.get('available_database_count', 0)}/{summary.get('expected_database_count', 5)}",
    ]
    if databases:
        lines.extend(("", "Bazy:"))
        for name, item in databases.items():
            marker = "✓" if item.get("ok") else "!"
            lines.append(f"  {marker} {name}: {human_size(item.get('size_bytes'))}")
    return "\n".join(lines)


def format_preflight(report: dict[str, Any]) -> str:
    ok = bool(report.get("ok"))
    lines = [
        "GOTOWOŚĆ PROJEKTU: " + ("GOTOWY" if ok else "WYMAGA POPRAWY"),
        "",
        f"Katalog docelowy: {report.get('target_root') or 'nie ustawiono'}",
        f"Włączone źródła: {report.get('enabled_source_count', 0)}",
        f"Źródła importowane do odbudowy: {report.get('memory_rebuild_source_count', 0)}",
        f"Źródła referencyjne — bez bezpośredniego importu: {report.get('catalog_only_source_count', 0)}",
        f"Źródła HTML używane tylko do kontroli: {report.get('html_control_source_count', 0)}",
    ]
    errors = list(report.get("errors") or [])
    if errors:
        lines.extend(("", "Co trzeba poprawić:"))
        lines.extend(f"  • {ERROR_LABELS.get(item, item)}" for item in errors)

    invalid_paths = [Path(str(item)) for item in report.get("missing_sources") or []]
    folder_entries = [path for path in invalid_paths if path.is_dir()]
    missing_files = [path for path in invalid_paths if not path.exists()]
    other_invalid = [path for path in invalid_paths if path.exists() and not path.is_dir() and not path.is_file()]

    if missing_files:
        lines.extend(("", "Nieistniejące pliki źródłowe:"))
        lines.extend(f"  • {item}" for item in missing_files)
    if folder_entries:
        lines.extend(("", "Foldery dodane omyłkowo jako pliki źródłowe:"))
        lines.extend(f"  • {item}" for item in folder_entries)
    if other_invalid:
        lines.extend(("", "Ścieżki, które nie wskazują na zwykłe pliki:"))
        lines.extend(f"  • {item}" for item in other_invalid)

    blocked = list(report.get("blocked_sources") or [])
    if blocked:
        lines.extend(("", "Zablokowane źródła:"))
        for item in blocked:
            lines.append(f"  • {item.get('path')}")
            for warning in item.get("warnings") or []:
                lines.append(f"      - {WARNING_LABELS.get(warning, warning)}")
    if ok:
        lines.extend(("", "Następny krok: uruchom „Plan bez zapisu”."))
    else:
        lines.extend(
            (
                "",
                "Najczęstsza naprawa:",
                "  1. Otwórz „Źródła pamięci”.",
                "  2. Wybierz „Usuń z projektu wpisy nieistniejące lub będące folderami”.",
                "  3. Wybierz „Przeskanuj folder źródeł”.",
                "  4. Wskaż folder zawierający ZIP-y/JSON-y i dodaj znalezione pliki.",
            )
        )
    return "\n".join(lines)


def format_plan(payload: dict[str, Any]) -> str:
    plan = payload.get("engine_plan", {}) if isinstance(payload, dict) else {}
    lines = [
        "PLAN BEZ ZAPISU",
        "",
        f"Plan poprawny: {_yes(bool(plan.get('ok')))}",
        f"Wybrane źródła: {plan.get('selected_source_count', 0)}",
        f"Źródła rozmów: {plan.get('chat_source_count', 0)}",
        f"Źródła dziennika: {plan.get('journal_source_count', 0)}",
        f"Źródła odrzucone: {plan.get('rejected_source_count', 0)}",
        f"Bazy porównawcze: {payload.get('baseline_count', 0)}",
        "",
        "Ten etap niczego nie zapisuje do baz docelowych.",
    ]
    rejected = plan.get("rejected") or []
    if rejected:
        lines.extend(("", "Odrzucone źródła:"))
        for item in rejected:
            lines.append(f"  • {item.get('path', item)}")
    return "\n".join(lines)


__all__ = [
    "PIPELINE_LABELS",
    "ROLE_LABELS",
    "TRUTH_LABELS",
    "baseline_title",
    "format_baseline",
    "format_plan",
    "format_preflight",
    "format_source",
    "source_title",
]
