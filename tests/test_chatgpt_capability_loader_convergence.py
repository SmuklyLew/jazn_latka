from __future__ import annotations

from pathlib import Path

from latka_jazn.version import PACKAGE_RELEASE_NAME, PACKAGE_VERSION


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_project_loader_is_pasteable_thin_loader_with_current_message_gate() -> None:
    text = _read("docs/runtime/CHATGPT_PROJECT_INSTRUCTIONS.txt")
    assert len(text) <= 5000
    assert "przeznaczoną do wklejenia do instrukcji Projektu/aplikacji ChatGPT" in text
    assert "Dla każdej wiadomości najpierw sprawdź faktycznie wywoływalną" in text
    assert "pełnego bieżącego toolsetu" in text
    assert "„installed”" in text
    assert "lista z poprzedniej wiadomości" in text
    assert "Nie wnioskuj z nazwy planu ChatGPT" in text
    assert "Jaźń Runtime" in text
    assert "Nie dziedzicz autoryzacji ani tool-exposure między wiadomościami" in text


def test_project_loader_does_not_invent_handoff_or_execution_route() -> None:
    text = _read("docs/runtime/CHATGPT_PROJECT_INSTRUCTIONS.txt")
    assert "`host_handoff` stosuj wyłącznie" in text
    assert "użytkownik zaakceptuje przekazanie" in text
    assert "bez wyniku SYSTEM-u nie wymyślaj jej" in text
    assert "Instrukcja Projektu nie może sama stworzyć capability" in text


def test_chatgpt_runbook_requires_complete_current_message_turn_toolset() -> None:
    text = _read("AGENTS.chatgpt.md")
    assert "Fresh-message app exposure gate" in text
    for tool_name in (
        "jazn_status",
        "jazn_generate_visible_reply",
        "jazn_resume_visible_reply",
        "jazn_finalize_reply",
    ):
        assert tool_name in text
    assert "current_message_toolset_observed=true" in text
    assert "Nie koduj polityki jako `plan == Plus/Pro/Business/...`" in text
    assert "Jaźń Runtime" in text


def test_release_version_tracks_current_distribution_identity() -> None:
    assert PACKAGE_VERSION == "119.2.0"
    assert PACKAGE_RELEASE_NAME == "remote-only-chatgpt-ingress-convergence"
