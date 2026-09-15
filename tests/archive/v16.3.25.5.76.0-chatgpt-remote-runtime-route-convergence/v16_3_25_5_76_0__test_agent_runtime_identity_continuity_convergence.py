from __future__ import annotations

from pathlib import Path

from latka_jazn.version import PACKAGE_RELEASE_NAME, PACKAGE_VERSION


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_root_agents_router_matches_main_first_dispatch() -> None:
    agents = _read("AGENTS.md")
    run_py = _read("run.py")
    main_py = _read("main.py")

    assert "main-first control plane" in agents
    assert "`run.py` jest publicznym, cienkim starterem użytkownika" in agents
    assert "`main.py` jest jedynym centralnym punktem sterowania" in agents
    assert "parser/usługi komend: `latka_jazn/cli.py`" in agents

    assert "runpy.run_path" in run_py
    assert "main.py" in run_py
    assert "argparse" not in run_py
    for forbidden in ("runtime-bootstrap", "host-finalize", "restart_daemon", "reload_daemon"):
        assert forbidden not in run_py

    assert "def main(argv: list[str] | None = None)" in main_py
    assert "def legacy_main(" in main_py
    assert "legacy_handler=legacy_main" in main_py


def test_chatgpt_runbook_requires_one_persistent_bridge() -> None:
    text = _read("AGENTS.chatgpt.md")

    assert "runtime-first, identity-by-lineage" in text
    assert "`main.py` jest jedynym centralnym control plane" in text
    assert "python -X utf8 run.py chat-gpt --session-id" in text
    assert "nie uruchamiaj nowej komendy CLI" in text
    assert "ten sam otwarty kanał" in text
    assert "nie wykonuje płatnych wywołań OpenAI API" in text
    assert "action=display_exact" in text
    assert "action=generate_then_finalize" in text
    assert "action=poll_runtime" in text
    assert "action=host_diagnostic" in text
    assert "must_not_claim_runtime_voice" in text
    assert "must_preserve_runtime_voice" in text
    assert "Narzędzia hosta są capability" in text


def test_chatgpt_project_instructions_remain_thin_loader() -> None:
    text = _read("docs/runtime/CHATGPT_PROJECT_INSTRUCTIONS.txt")

    assert text.startswith("# LOADER SYSTEMU JAŹNI\n")
    assert len(text) <= 5000
    assert "`AGENTS.md`" in text
    assert "`AGENTS.chatgpt.md`" not in text
    assert "runbook odpowiedni dla bieżącego hosta lub zadania" in text
    assert "run.py" in text
    assert "main.py" in text
    assert "raz na sesję wykonawczą" in text
    assert "Nie uruchamiaj nowego procesu CLI" in text
    assert "OPENAI_API_KEY" in text
    assert "persona" not in text.lower()
    assert "osobowo" not in text.lower()
    assert "tożsamo" not in text.lower()
    assert "Łatka" not in text


def test_codex_runbook_declares_main_first_boundary() -> None:
    text = _read("AGENTS.codex.md")

    assert "AGENTS.override.md" in text
    assert "`AGENTS.codex.md` jest projektowym runbookiem" in text
    assert "`run.py`" in text
    assert "cienkim starterem" in text
    assert "`main.py`" in text
    assert "centralnym" in text
    assert "`latka_jazn/cli.py`" in text
    assert "<= 5000" in text


def test_ollama_runbook_keeps_model_backend_outside_identity_ownership() -> None:
    text = _read("AGENTS.ollama.md")

    assert "nie jest system promptem" in text.lower()
    assert "nie jest operatorem systemu" in text.lower()
    assert "backendem generowania kandydata językowego" in text
    assert "run.py chat-ollama" in text
    assert "main.py chat-ollama" in text
    assert "latka_jazn.cli" in text
    assert "POST /api/chat" in text
    assert "GET /api/tags" in text
    assert "`SYSTEM`" in text
    assert "`messages`" in text


def test_readme_exposes_thin_launcher_and_central_main() -> None:
    text = _read("README.md")

    assert "`run.py` jest publicznym **cienkim starterem**" in text
    assert "`main.py` jest jedynym centralnym control plane" in text
    assert "python -X utf8 run.py chat-gpt --session-id" in text
    assert "ChatGPT, Codex i Ollama pełnią różne role" in text


def test_release_line_advances_to_accepted_visible_turn_convergence() -> None:
    version = tuple(int(part) for part in PACKAGE_VERSION.split("."))

    assert version >= (16, 3, 25, 5, 61)
    assert PACKAGE_RELEASE_NAME
