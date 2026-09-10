from __future__ import annotations

from pathlib import Path

from latka_jazn.version import PACKAGE_RELEASE_NAME, PACKAGE_VERSION


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_root_agents_router_matches_real_operator_dispatch() -> None:
    agents = _read("AGENTS.md")
    run_py = _read("run.py")

    assert "`run.py` jest kanonicznym operatorem" in agents
    assert "latka_jazn.cli.main()" in agents
    assert "`main.py`" in agents
    assert "techniczny punkt zgodności" in agents

    assert "from latka_jazn.cli import main" in run_py
    assert "from main import main as _legacy_runtime_main" in run_py
    assert "_normalize_operator_argv" in run_py
    assert "runtime-bootstrap" in run_py
    assert "host-finalize" in run_py


def test_chatgpt_runbook_binds_host_to_operator_before_visible_reply() -> None:
    text = _read("AGENTS.chatgpt.md")

    assert "runtime-first, identity-by-lineage" in text
    assert "`latka_jazn.cli` jest głównym dispatcherem" in text
    assert "python -X utf8 run.py chat-gpt" in text
    assert "action=display_exact" in text
    assert "action=generate_then_finalize" in text
    assert "action=poll_runtime" in text
    assert "action=host_diagnostic" in text
    assert "must_not_claim_runtime_voice" in text
    assert "must_preserve_runtime_voice" in text
    assert "Narzedzia hosta sa capability" not in text
    assert "Narzędzia hosta są capability" in text
    assert "Host nie implementuje w ten sposób funkcji runtime" in text
    assert "`main.py`" in text
    assert "równorzędnego operatora" in text


def test_chatgpt_project_instructions_remain_thin_loader() -> None:
    text = _read("docs/runtime/CHATGPT_PROJECT_INSTRUCTIONS.txt")

    assert text.startswith("# LOADER SYSTEMU JAŹNI\n")
    assert len(text) <= 5000
    assert "`AGENTS.md`" in text
    assert "`AGENTS.chatgpt.md`" not in text
    assert "runbook odpowiedni dla bieżącego hosta lub zadania" in text
    assert "run.py" in text
    assert "main.py" in text
    assert "persona" not in text.lower()
    assert "osobowo" not in text.lower()
    assert "tożsamo" not in text.lower()
    assert "Łatka" not in text


def test_codex_runbook_declares_custom_runbook_discovery_boundary() -> None:
    text = _read("AGENTS.codex.md")

    assert "AGENTS.override.md" in text
    assert "`AGENTS.codex.md` jest projektowym runbookiem" in text
    assert "`run.py` pozostaje jedynym publicznym operatorem" in text
    assert "`latka_jazn/cli.py`" in text
    assert "`main.py`" in text
    assert "<= 5000" in text


def test_ollama_runbook_keeps_model_backend_outside_identity_ownership() -> None:
    text = _read("AGENTS.ollama.md")

    assert "nie jest system promptem" in text.lower()
    assert "nie jest operatorem systemu" in text.lower()
    assert "backendem generowania kandydata językowego" in text
    assert "run.py chat-ollama" in text
    assert "latka_jazn.cli" in text
    assert "POST /api/chat" in text
    assert "GET /api/tags" in text
    assert "`SYSTEM`" in text
    assert "`messages`" in text


def test_readme_exposes_single_operator_and_compatibility_layer() -> None:
    text = _read("README.md")

    assert "Publicznym operatorem jest wyłącznie `run.py`" in text
    assert "latka_jazn.cli.main()" in text
    assert "main.py tylko dla kontrolowanych ścieżek zgodnościowych" in text
    assert "ChatGPT, Codex i Ollama pełnią różne role" in text


def test_release_line_advances_to_v58_pending_host_request_continuity_recovery() -> None:
    version = tuple(int(part) for part in PACKAGE_VERSION.split("."))

    assert version >= (16, 3, 25, 5, 58)
    assert PACKAGE_RELEASE_NAME == "pending-host-request-continuity-recovery"
