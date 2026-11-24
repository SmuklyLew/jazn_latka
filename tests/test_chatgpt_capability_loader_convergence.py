from __future__ import annotations

import json

from pathlib import Path

from latka_jazn.version import PACKAGE_RELEASE_NAME, PACKAGE_VERSION


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_project_loader_is_pasteable_thin_loader_with_current_message_gate() -> None:
    text = _read("docs/runtime/CHATGPT_PROJECT_INSTRUCTIONS.txt")
    assert len(text) <= 5000
    assert "cienkim loaderem Projektu ChatGPT" in text
    assert "Dla każdej wiadomości sprawdź bez zbędnych wywołań" in text
    assert "Dotyczy to WYŁĄCZNIE zdalnego MCP" in text
    assert "Brak `jazn_*` NIE blokuje lokalnego SYSTEM ZIP" in text
    assert "Jaźń Runtime" in text
    assert "Długi czas oczekiwania hosta nie dowodzi startu procesu" in text
    assert "Brak remote = `host_diagnostic`" in text
    assert "najwyżej jedną minimalną próbę utworzenia procesu" in text
    assert "kanonicznego SYSTEM discovery/bootstrapu" in text
    assert "Granice uprawnień loadera" in text
    assert "Loader nie rozszerza uprawnień" in text
    assert "Dostęp do narzędzia nie stanowi zgody na zapis" in text
    assert "Polecenie użytkownika autoryzuje jedynie zlecone działanie" in text
    assert "Bez jawnego polecenia użytkownika loader nie może:" in text
    assert "runtime nie zastępuje zgody hosta" in text


def test_project_loader_declares_remote_only_and_separate_recovery() -> None:
    text = _read("docs/runtime/CHATGPT_PROJECT_INSTRUCTIONS.txt")
    ordinary, recovery = text.split("## 2. Minimalny bootstrap — wyłącznie jawny `operator_recovery`", 1)
    assert "Zwykła rozmowa ChatGPT = remote-only" in ordinary
    assert "Brak remote = `host_diagnostic`" in ordinary
    assert "Nie wykonuj lokalnego probe" in ordinary
    assert "najwyżej jedną minimalną próbę" not in ordinary
    assert "najwyżej jedną minimalną próbę" in recovery
    assert "Ordinary remote-only nie używa handoffu" in recovery
    assert "filesystem/paczka pozostają `unknown`" in recovery


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
    ordinary, recovery = text.split("## 3. Warm, resume i cold — wyłącznie operator_recovery", 1)
    assert "Jedyna trasa ordinary-chat" in ordinary
    assert "Brak kompletnego toolsetu lub świeżej zweryfikowanej gotowości" in ordinary
    assert "ani handoffu w ordinary-chat" in ordinary
    assert "Sekcje 3–6 dotyczą jawnie autoryzowanego lokalnego recovery" in recovery
    assert "w ordinary `remote_only` handoff pozostaje zabroniony" in recovery


def test_release_version_tracks_current_distribution_identity() -> None:
    startup = json.loads(
        (ROOT / "latka_jazn/resources/startup_contract.json").read_text(encoding="utf-8")
    )
    deployment = json.loads(
        (ROOT / "deploy/chatgpt_mcp/deployment.contract.json").read_text(encoding="utf-8")
    )
    assert startup["version"] == PACKAGE_VERSION
    assert deployment["runtime_version"] == f"{PACKAGE_VERSION}-{PACKAGE_RELEASE_NAME}"