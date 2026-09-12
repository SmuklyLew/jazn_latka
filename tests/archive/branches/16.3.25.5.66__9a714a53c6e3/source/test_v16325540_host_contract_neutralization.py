from __future__ import annotations

from pathlib import Path

from latka_jazn.core.chat_command_contract import build_chatgpt_host_presentation_packet
from latka_jazn.version import PACKAGE_RELEASE_NAME, PACKAGE_VERSION


ROOT = Path(__file__).resolve().parents[1]


def test_poll_presentation_exposes_neutral_runtime_voice_contract_with_legacy_alias() -> None:
    payload = {
        "chatgpt_host_bridge": {
            "phase": "runtime_result_pending",
            "daemon_request_id": "request-123",
            "poll_command": "python -X utf8 run.py chat-gpt --daemon-result request-123",
        }
    }
    packet = build_chatgpt_host_presentation_packet(payload)

    assert packet["action"] == "poll_runtime"
    assert packet["must_not_claim_runtime_voice"] is True
    assert packet["must_not_claim_latka_voice"] is packet["must_not_claim_runtime_voice"]
    assert packet["must_preserve_runtime_voice"] is False
    assert packet["must_preserve_latka_voice"] is packet["must_preserve_runtime_voice"]


def test_generate_then_finalize_exposes_neutral_preserve_contract_with_legacy_alias() -> None:
    payload = {
        "chatgpt_host_bridge": {
            "phase": "host_visible_generation_requested",
            "host_must_generate_visible_reply": True,
            "pending_request_persisted": True,
            "host_request_contract_hash": "0" * 64,
            "host_generation_policy": {
                "voice_continuity_policy": {
                    "active_runtime_first_person_voice_required": True,
                }
            },
        }
    }
    packet = build_chatgpt_host_presentation_packet(payload)

    assert packet["action"] == "generate_then_finalize"
    assert packet["must_not_claim_runtime_voice"] is False
    assert packet["must_not_claim_latka_voice"] is packet["must_not_claim_runtime_voice"]
    assert packet["must_preserve_runtime_voice"] is True
    assert packet["must_preserve_latka_voice"] is packet["must_preserve_runtime_voice"]


def test_chatgpt_project_loader_is_system_only_and_fits_plus_limit() -> None:
    text = (ROOT / "docs/runtime/CHATGPT_PROJECT_INSTRUCTIONS.txt").read_text(encoding="utf-8")

    assert text.startswith("# LOADER SYSTEMU JAŹNI\n")
    assert len(text) <= 5000
    assert "Łatka" not in text
    assert "persona" not in text.lower()
    assert "osobowo" not in text.lower()
    assert "tożsamo" not in text.lower()


def test_chatgpt_runbook_uses_neutral_canonical_host_fields() -> None:
    text = (ROOT / "AGENTS.chatgpt.md").read_text(encoding="utf-8")

    assert "must_not_claim_runtime_voice" in text
    assert "must_preserve_runtime_voice" in text
    assert "must_not_claim_latka_voice" not in text
    assert "must_preserve_latka_voice" not in text
    assert "Łatka" not in text


def test_ollama_runbook_is_integration_contract_not_model_prompt() -> None:
    text = (ROOT / "AGENTS.ollama.md").read_text(encoding="utf-8")

    assert "nie jest system promptem" in text.lower()
    assert "`messages`" in text
    assert "`SYSTEM`" in text
    assert "POST /api/chat" in text
    assert "GET /api/tags" in text


def test_codex_runbook_checks_actual_custom_instruction_limit() -> None:
    text = (ROOT / "AGENTS.codex.md").read_text(encoding="utf-8")

    assert "<= 5000" in text
    assert "<= 8000" not in text


def test_release_line_preserves_host_contract_neutralization_floor() -> None:
    version = tuple(int(part) for part in PACKAGE_VERSION.split("."))
    assert version >= (16, 3, 25, 5, 40)
    assert PACKAGE_RELEASE_NAME
