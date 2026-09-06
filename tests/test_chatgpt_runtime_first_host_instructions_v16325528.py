from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_agents_router_makes_run_py_primary_executable_authority() -> None:
    text = (ROOT / "AGENTS.md").read_text(encoding="utf-8")

    assert "`run.py` jest kanonicznym operatorem i głównym wykonawczym wejściem" in text
    assert "persistent runtime active" in text
    assert "verified runtime turn" in text
    assert "One-shot nie może być przedstawiany jako persistent proces" in text
    assert "`main.py` traktuj wyłącznie jako techniczny punkt zgodności" in text


def test_chatgpt_runbook_is_runtime_first_and_persistent_when_possible() -> None:
    text = (ROOT / "AGENTS.chatgpt.md").read_text(encoding="utf-8")

    assert "## 0. Zasada nadrzędna: runtime-first" in text
    assert "python -X utf8 run.py start" in text
    assert "python -X utf8 run.py status --json" in text
    assert "python -X utf8 run.py chat-gpt --" in text
    assert "nie uruchamiaj samego `python run.py`" in text
    assert "one-shot nie jest persistent procesem" in text
    assert "Nie używaj `nohup`, `&`, `screen`, `tmux` ani własnego `subprocess.Popen`" in text
    assert "Jeżeli istnieje `/mnt/data`, sprawdź go jako pierwszy kandydat" in text
    assert "Nie traktuj `/mnt/data` jako gwarantowanego kontraktu platformy" in text


def test_local_run_py_precedes_optional_mcp_transport() -> None:
    text = (ROOT / "AGENTS.chatgpt.md").read_text(encoding="utf-8")

    local_index = text.index("preferowanym wejściem hosta jest")
    mcp_index = text.index("Jeżeli lokalny operator nie jest dostępny, ale prywatne narzędzia MCP")
    assert local_index < mcp_index


def test_project_loader_stays_thin_and_points_to_runtime_first_contract() -> None:
    text = (ROOT / "docs/runtime/CHATGPT_PROJECT_INSTRUCTIONS.txt").read_text(encoding="utf-8")

    assert len(text) <= 8000
    assert "`AGENTS.md`" in text
    assert "`AGENTS.chatgpt.md`" in text
    assert "`run.py` jako główne wykonawcze wejście" in text
    assert "persistent daemona" in text
    assert "one-shot" in text
    assert "HOST_ROUTING_BYPASS" not in text
    assert "final_visible_text" not in text
