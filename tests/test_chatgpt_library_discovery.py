from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_project_loader_searches_library_before_declaring_system_zip_absent() -> None:
    text = _read("docs/runtime/CHATGPT_PROJECT_INSTRUCTIONS.txt")

    assert "Bibliotekę ChatGPT" in text
    assert "sprawdź ją przed stwierdzeniem braku SYSTEM ZIP" in text
    assert "nie jest ścieżką OS" in text
    assert "zmaterializuj dokładne bajty" in text
    assert "ponownie zweryfikuj rozmiar i zaufany SHA-256" in text
    assert "Sprzeczne kopie/metadane kończ fail-closed" in text
    assert len(text) <= 5000


def test_chatgpt_runbook_separates_library_identity_from_os_paths() -> None:
    text = _read("AGENTS.chatgpt.md")

    assert "brak paczki w `/mnt/data` nie dowodzi jej braku w Bibliotece ChatGPT" in text
    assert "Logiczna ścieżka Biblioteki, `file_id` ani inny uchwyt hosta nie są ścieżką systemu plików" in text
    assert "zmaterializuj jako dokładne surowe bajty" in text
    assert "Dopiero zweryfikowana lokalna kopia może wejść do istniejącego bootstrapu" in text


def test_chatgpt_runbook_fails_closed_on_conflicting_library_candidates() -> None:
    text = _read("AGENTS.chatgpt.md")

    assert "sprzeczny rozmiar, SHA-256 albo metadane" in text
    assert "zakończ fail-closed" in text
    assert "library_surface_unavailable" in text
    assert "nie jest dowodem, że paczki w Bibliotece nie ma" in text


def test_library_materialization_does_not_promote_memory_package_to_system_root() -> None:
    text = _read("AGENTS.chatgpt.md")

    assert "Materializacja SYSTEM nie materializuje automatycznie MEMORY" in text
    assert "profil `memory` nadal nie może stać się `active_root`" in text
