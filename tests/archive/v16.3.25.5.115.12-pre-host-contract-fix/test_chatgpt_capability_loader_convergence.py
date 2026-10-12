from __future__ import annotations

from pathlib import Path

from latka_jazn.version import PACKAGE_RELEASE_NAME, PACKAGE_VERSION


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_project_loader_is_pasteable_thin_loader_with_current_message_gate() -> None:
    text = _read("docs/runtime/CHATGPT_PROJECT_INSTRUCTIONS.txt")
    assert len(text) <= 5000
    assert "cienkim loaderem Projektu ChatGPT" in text
    assert "Dla każdej wiadomości najpierw sprawdź faktycznie wywoływalną" in text
    assert "pełnego bieżącego toolsetu" in text
    assert "„Installed”" in text
    assert "historyczna lista narzędzi" in text
    assert "Nie wnioskuj z nazwy planu ChatGPT" in text
    assert "Jaźń Runtime" in text
    assert "Nie dziedzicz autoryzacji ani tool-exposure między wiadomościami" in text
    assert "Nie wolno zakończyć diagnozy" in text
    assert "realną, najwyżej jedną minimalną próbę utworzenia procesu" in text
    assert "obowiązkowo przejdź do SYSTEM discovery/bootstrapu" in text
    assert "Granice uprawnień loadera" in text
    assert "Loader nie rozszerza uprawnień" in text
    assert "Dostęp do narzędzia nie stanowi zgody na zapis" in text
    assert "Polecenie użytkownika autoryzuje jedynie zlecone działanie" in text
    assert "Bez jawnego polecenia użytkownika loader nie może:" in text
    assert "runtime nie zastępuje zgody hosta" in text


def test_project_loader_declares_bounded_local_fallback_without_automatic_handoff() -> None:
    text = _read("docs/runtime/CHATGPT_PROJECT_INSTRUCTIONS.txt")
    assert "hybrid/adaptive remote-first" in text
    assert "bounded local fallback" in text
    assert "najwyżej jedną minimalną próbę" in text
    assert "Ordinary hybrid/adaptive ingress nie używa automatycznego handoffu" in text
    assert "filesystem/paczka pozostają `unknown`" in text


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
    assert PACKAGE_VERSION == "16.3.25.5.115.12"
    assert PACKAGE_RELEASE_NAME == "runtime-activity-freshness-convergence"
