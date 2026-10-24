"""Operator-only, version-scoped manual acceptance queue for Studio Jaźni.

Test definitions ship with the source. Results, private notes and evidence
references never enter Git, SYSTEM, runtime workspace or private MEMORY.
No operations in this module execute test commands or claim CI/model results.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import uuid
from typing import Any

from latka_jazn.core.version_source import read_runtime_version_from_version_py
from latka_jazn.tools.application_shell.operator_paths import (
    operator_file, validate_operator_path,
)

SCHEMA = "jazn_studio_manual_acceptance/v1"
APP_ID = "jazn_studio_manual_acceptance"
MAX_SIZE = 1024 * 1024
OUTCOMES = ("passed", "failed", "blocked")
SENSITIVE = re.compile(
    r"(?i)(?:-----BEGIN [A-Z ]*PRIVATE KEY-----|"
    r"\bBearer\s+\S+|\b(?:password|secret|api[_-]?key|token)\s*[:=]\s*\S+|"
    r"\bsk-[A-Za-z0-9_-]{12,})"
)

# A manual verification catalogue, not self-executing shell commands.
# Adding a new record in a later release reopens it for that release.
CATALOG: tuple[dict[str, str], ...] = (
    {"id": "gui-daemon", "category": "Runtime", "title": "Uruchomienie izolowanej instancji z GUI",
     "steps": "Wybierz osobny katalog SYSTEM, pusty workspace i wolny port. Uruchom runtime z Usługi i procesy; odczytaj /live oraz status --json.",
     "expected": "Właściwy root i wersja, zgodny PID/instance_id, identity/root matches oraz conversation_ready=true; bez wpływu na inne instancje."},
    {"id": "ollama-two-turns", "category": "Czat", "title": "Dwie rzeczywiste tury z lokalną Ollamą",
     "steps": "Połącz Studio z izolowanym daemonem, podaj syntetyczny kod i sprawdź odpowiedź. W następnej turze zapytaj o kod bez powtarzania go.",
     "expected": "Obie odpowiedzi są widoczne i zaakceptowane; druga odtwarza informację w tej samej session_id; odrębne request_id/turn_id/trace_id."},
    {"id": "chat-reconnect", "category": "Czat", "title": "Rozłączenie i ponowne połączenie klienta",
     "steps": "Po zaakceptowaniu pierwszej tury rozłącz transport GUI, podłącz ponownie do tego samego endpointu i wyślij następną turę.",
     "expected": "Zachowana session_id i poprawna finalizacja bez utraty kontekstu oraz bez podwójnego wyświetlania."},
    {"id": "chat-resume", "category": "Czat", "title": "Wznowienie nierozstrzygniętej tury",
     "steps": "W testowym workspace przerwij transport po wysłaniu wiadomości i użyj Wznów wynik dla tego samego request_id.",
     "expected": "Brak ponownego wysłania wiadomości; jedna zaakceptowana finalizacja i potwierdzenie dopiero po jej wyświetleniu."},
    {"id": "daemon-restart", "category": "Runtime", "title": "Trwałość sesji po kontrolowanym restarcie",
     "steps": "Dopiero po poprzednich testach zatrzymaj i uruchom wyłącznie własny testowy daemon; ponownie potwierdź jego tożsamość i sesję.",
     "expected": "Brak wpływu na obce PID/porty, poprawne nowe instance_id i wynik testu ciągłości lub jawna porażka."},
    {"id": "smoke-isolation", "category": "Bezpieczeństwo", "title": "Izolacja package-smoke i markerów",
     "steps": "Wykonaj test pakietu w oddzielnym workspace i porównaj przed/po znaczniki operacyjnych daemonów bez ich modyfikowania.",
     "expected": "Test nie zapisuje markerów w cudzym workspace, nie usuwa aktywnych plików i nie ingeruje w MEMORY."},
    {"id": "config-persistence", "category": "Konfiguracja", "title": "Konfiguracja ROOT i uruchomienie bez ręcznego ENV",
     "steps": "Zapisz ustawienia w ROOT/jazn_system_config.json i Studio; uruchom nową testową instancję bez ręcznego przepisywania każdego ENV.",
     "expected": "Loader stosuje jawne priorytety, dane pozostają po restarcie Studio, sekrety są oddzielone i ignorowane przez Git."},
    {"id": "studios-parity", "category": "Studia", "title": "Parzystość wszystkich 12 studiów",
     "steps": "Przejdź macierz STUDIO_MIGRATION.md; dla każdego narzędzia sprawdź odpowiadającą mu stronę Qt, operacje, walidację, błędy i ustawienia.",
     "expected": "12 oddzielnych dowodów odbioru; starsze okno uruchamiane z Qt nie jest pełną migracją."},
    {"id": "offline-exe", "category": "Dystrybucja", "title": "EXE offline na Windows",
     "steps": "Uruchom wydany plik EXE w odizolowanym środowisku offline; sprawdź instalację zależności, uruchomienie i podstawowe ekrany.",
     "expected": "Rzeczywista praca bez niedeklarowanych pobrań; podpisane raporty i brak false-positive readiness."},
    {"id": "ui-accessibility", "category": "GUI", "title": "Klawiatura, skalowanie DPI i motywy",
     "steps": "Sprawdź na Windows i/lub Unix minimum 860x580, DPI, fokusa z klawiatury, czytelność, własny kolor i zwijanie panelu logów.",
     "expected": "Wszystkie kontrolki osiągalne, bez przycięć i z dostępnie opisanymi operacjami."},
)

def scope_version(root: Path) -> str:
    return read_runtime_version_from_version_py(root) or "unverified-source"


def result_path(root: Path) -> Path:
    return operator_file(APP_ID, root, "manual_results.json")


def _empty() -> dict[str, Any]:
    return {"schema_version": SCHEMA, "results": [], "archive": [], "custom_tests": []}


def _checked_text(value: str, maximum: int, field: str) -> str:
    if not isinstance(value, str) or len(value) > maximum or "\x00" in value:
        raise ValueError("Nieprawidłowa długość lub treść pola: " + field)
    if SENSITIVE.search(value):
        raise ValueError("Nie zapisuj sekretów ani tokenów w danych odbioru: " + field)
    return value.strip()


def load(root: Path) -> tuple[dict[str, Any], str | None]:
    path = result_path(root)
    if not path.exists():
        return _empty(), None
    raw = path.read_bytes()
    if len(raw) > MAX_SIZE:
        raise ValueError("Zbyt duży lokalny plik wyników odbioru")
    data = json.loads(raw.decode("utf-8-sig"))
    if (not isinstance(data, dict) or set(data) != {"schema_version", "results", "archive", "custom_tests"}
            or data["schema_version"] != SCHEMA
            or any(not isinstance(data[key], list) or len(data[key]) > 2500
                   for key in ("results", "archive", "custom_tests"))):
        raise ValueError("Nieznana lub uszkodzona struktura lokalnych wyników odbioru")
    return data, sha256(raw).hexdigest()


def catalog(root: Path, data: dict[str, Any]) -> list[dict[str, str]]:
    items = [dict(row) for row in CATALOG]
    for row in data["custom_tests"]:
        if not isinstance(row, dict) or set(row) != {"id", "category", "title", "steps", "expected"}:
            raise ValueError("Uszkodzona definicja własnego testu")
        if not isinstance(row["id"], str) or not re.fullmatch(r"local-[0-9a-f]{32}", row["id"]):
            raise ValueError("Nieprawidłowy identyfikator testu")
        items.append({k: _checked_text(v, 3000, k) for k, v in row.items()})
    ids = [row["id"] for row in items]
    if len(ids) != len(set(ids)):
        raise ValueError("Powtarzające się identyfikatory testów")
    return items


def outcome(data: dict[str, Any], test_id: str, version: str) -> dict[str, Any] | None:
    for section in ("archive", "results"):
        for row in reversed(data[section]):
            if not isinstance(row, dict):
                raise ValueError("Nieprawidłowy rekord odbioru")
            if row.get("test_id") == test_id and row.get("version") == version:
                return dict(row, archived=(section == "archive"))
    return None


def _persist(root: Path, data: dict[str, Any], expected: str | None) -> str:
    path = result_path(root)
    _, actual = load(root)
    if expected != actual:
        raise ValueError("Plik wyników został zmieniony; odśwież listę przed zapisem")
    raw = (json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
    if len(raw) > MAX_SIZE:
        raise ValueError("Przekroczony limit wyników odbioru")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = validate_operator_path(path.with_suffix(".tmp"), root)
    if tmp.exists():
        raise ValueError("Pozostał plik tymczasowy; nie nadpisano wyników")
    try:
        with tmp.open("xb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        # Backup is unique and append-only, and never contains SYSTEM secrets.
        if path.exists():
            backup = validate_operator_path(path.with_name(path.name + ".backup-" + uuid.uuid4().hex), root)
            with backup.open("xb") as handle:
                handle.write(path.read_bytes())
                handle.flush()
                os.fsync(handle.fileno())
        # Do not silently replace a concurrent manual edit.
        _, before_replace = load(root)
        if before_replace != expected:
            raise ValueError("Wyniki zmieniły się podczas zapisu; zachowano backup")
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()
    return sha256(raw).hexdigest()


def add_custom(root: Path, expected: str | None, title: str, steps: str, result: str) -> str:
    data, current = load(root)
    if current != expected:
        raise ValueError("Odśwież listę przed dodaniem testu")
    title = _checked_text(title, 160, "tytuł")
    steps = _checked_text(steps, 3000, "kroki")
    result = _checked_text(result, 3000, "oczekiwany wynik")
    if not all((title, steps, result)):
        raise ValueError("Wypełnij tytuł, kroki i oczekiwany wynik")
    data["custom_tests"].append({"id": "local-" + uuid.uuid4().hex, "category": "Własny",
                                  "title": title, "steps": steps, "expected": result})
    return _persist(root, data, expected)


def save_result(root: Path, expected: str | None, test_id: str, status: str,
                note: str, evidence: str) -> str:
    data, current = load(root)
    if current != expected:
        raise ValueError("Odśwież listę przed zapisem")
    if status not in OUTCOMES or test_id not in {t["id"] for t in catalog(root, data)}:
        raise ValueError("Nieznany test lub wynik")
    note = _checked_text(note, 3000, "notatka")
    evidence = _checked_text(evidence, 800, "dowód")
    version = scope_version(root)
    if outcome(data, test_id, version) and any(
        r.get("test_id") == test_id and r.get("version") == version for r in data["archive"]
    ):
        raise ValueError("Test jest w archiwum tej wersji. Nowe wykonanie wymaga nowej wersji.")
    data["results"] = [r for r in data["results"]
                       if not (r.get("test_id") == test_id and r.get("version") == version)]
    data["results"].append({"test_id": test_id, "version": version, "status": status,
                            "note": note, "evidence": evidence,
                            "updated_utc": datetime.now(timezone.utc).isoformat()})
    return _persist(root, data, expected)


def archive_result(root: Path, expected: str | None, test_id: str) -> str:
    data, current = load(root)
    if current != expected:
        raise ValueError("Odśwież listę przed archiwizacją")
    version = scope_version(root)
    record = next((r for r in data["results"]
                   if r.get("test_id") == test_id and r.get("version") == version), None)
    if not record or record.get("status") != "passed" or not record.get("evidence") or not record.get("note"):
        raise ValueError("Archiwizacja wymaga wyniku PASS, notatki i dowodu")
    data["results"].remove(record)
    data["archive"].append(dict(record, archived_utc=datetime.now(timezone.utc).isoformat()))
    return _persist(root, data, expected)
