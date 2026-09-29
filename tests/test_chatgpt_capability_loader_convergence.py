from __future__ import annotations

from pathlib import Path

from latka_jazn.version import PACKAGE_RELEASE_NAME, PACKAGE_VERSION


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_project_loader_requires_callable_current_turn_capability() -> None:
    text = _read("docs/runtime/CHATGPT_PROJECT_INSTRUCTIONS.txt")

    assert len(text) <= 5000
    assert "faktycznie wywoływalne w bieżącej turze" in text
    assert "wynik wyszukiwania katalogu pluginów" in text
    assert "stan „installed”" in text
    assert "Connector innej usługi, np. GitHub lub Drive" in text
    assert "nie promuj zdalnej trasy" in text


def test_project_loader_does_not_invent_handoff_or_execution_route() -> None:
    text = _read("docs/runtime/CHATGPT_PROJECT_INSTRUCTIONS.txt")

    assert "`host_handoff` nie jest automatycznym fallbackiem" in text
    assert "użytkownik zaakceptuje przekazanie" in text
    assert "Odrzucenie lub brak handoff kończy tę trasę" in text
    assert "bez wyniku SYSTEM-u nie fabrykuj `execution_route`" in text
    assert "Instrukcja Projektu nie może sama stworzyć capability" in text


def test_chatgpt_runbook_requires_callable_jazn_connector_evidence() -> None:
    text = _read("AGENTS.chatgpt.md")

    assert "Dowód capability hosta musi dotyczyć bieżącej powierzchni i bieżącej tury" in text
    assert "akcje są rzeczywiście wywoływalne przez aktualny host" in text
    assert "Wynik wyszukiwania katalogu pluginów" in text
    assert "ogólny connector innej usługi (np. GitHub/Drive)" in text
    assert "nie może promować `remote_runtime`" in text


def test_chatgpt_runbook_treats_declined_handoff_as_unavailable_for_attempt() -> None:
    text = _read("AGENTS.chatgpt.md")

    assert "`host_handoff` służy wyłącznie do przekazania wykonania" in text
    assert "Jeżeli handoff został jawnie odrzucony" in text
    assert "Nie ponawiaj handoff w tej samej próbie" in text


def test_release_version_tracks_display_exact_envelope_revalidation() -> None:
    assert PACKAGE_VERSION == "16.3.25.5.90.2"
    assert PACKAGE_RELEASE_NAME == "display-exact-envelope-revalidation-convergence"
