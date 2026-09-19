from __future__ import annotations

import json
from pathlib import Path

import main as main_module
import latka_jazn.cli as cli_module
from latka_jazn.bootstrap.chatgpt_host_preflight import run_host_preflight_cli
from latka_jazn.config import JaznConfig
from latka_jazn.core import bridge_discovery
from latka_jazn.core.chat_command_contract import chatgpt_result_has_displayable_host_final
from latka_jazn.core.host_visible_finalization import sha256_host_visible_text
from latka_jazn.version import PACKAGE_RELEASE_NAME, PACKAGE_VERSION


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_phase_result_ready_is_not_hidden_behind_poll_runtime(monkeypatch, tmp_path: Path) -> None:
    observed: dict[str, object] = {}

    def fake_resolve_daemon_user_text_binding(**_kwargs):
        return "Dobry wieczór", None

    def fake_attach(result, *, config, user_text, chat_bridge_meta):
        observed["user_text"] = user_text
        observed["bridge"] = dict(chat_bridge_meta)
        result["chatgpt_host_presentation"] = {
            "action": "generate_then_finalize",
            "turn_id": "turn-ready",
        }
        return result

    monkeypatch.setattr(
        main_module,
        "_resolve_daemon_user_text_binding",
        fake_resolve_daemon_user_text_binding,
    )
    monkeypatch.setattr(main_module, "attach_chatgpt_host_contract", fake_attach)

    payload = {
        "ok": True,
        "request_id": "request-ready",
        "done": False,
        "phase_result_ready": True,
        "job_status": "awaiting_host_finalization",
        "result": {
            "ok": True,
            "chatgpt_host_bridge": {
                "phase": "host_visible_generation_requested",
                "turn_id": "turn-ready",
                "trace_id": "trace-ready",
            },
        },
    }
    result = main_module._prepare_chatgpt_daemon_presentation(
        cfg=JaznConfig(root=tmp_path),
        payload=payload,
        request_id="request-ready",
    )

    assert result["chatgpt_host_presentation"]["action"] == "generate_then_finalize"
    assert result["daemon_job"]["phase_result_ready"] is True
    assert result["daemon_job"]["done"] is False
    assert observed["user_text"] == "Dobry wieczór"


def test_chat_gpt_public_spelling_uses_central_option_surface() -> None:
    observed_args: list[str] = []

    def fake_legacy(args: list[str]) -> int:
        observed_args[:] = args
        return 23

    rc = cli_module.main(
        [
            "chat-gpt",
            "--session-id",
            "stable-session",
            "--daemon-result",
            "request-123",
        ],
        legacy_handler=fake_legacy,
    )

    assert rc == 23
    assert observed_args[0:2] == ["--root", str(ROOT)]
    assert observed_args[2:] == [
        "--chat-gpt",
        "--session-id",
        "stable-session",
        "--daemon-result",
        "request-123",
    ]


def test_host_preflight_without_input_is_truthful_and_runnable(capsys) -> None:
    rc = run_host_preflight_cli(["--json"])
    captured = capsys.readouterr()
    assert rc == 0
    payload = json.loads(captured.out)
    assert payload["ok"] is True
    assert payload["environment_state"] == "available"
    assert payload["filesystem_state"] == "observed"
    assert payload["package_state"] == "unknown"
    assert payload["runtime_state"] == "unverified"


def test_bridge_discovery_separates_daemon_liveness_from_visible_turn_readiness(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        bridge_discovery,
        "status_daemon",
        lambda *_args, **_kwargs: {"active_state": "active_trusted"},
    )
    payload = bridge_discovery.discover_runtime_bridges(JaznConfig(root=tmp_path))
    chatgpt = payload["chatgpt_bridge"]

    assert chatgpt["transport"] == "persistent_stdio_jsonl"
    assert chatgpt["transport_selection"] == "capability_negotiated"
    assert chatgpt["fallback_transport"] == "daemon_bound_transactional_turns"
    assert chatgpt["daemon_transactional_resume_supported"] is True
    assert chatgpt["pipe_lifetime_is_identity"] is False
    assert chatgpt["accepted_visible_turn_required"] is True
    assert chatgpt["visible_turn_readiness"] == "accepted_final_visible_text_only"
    assert chatgpt["uses_openai_api"] is False


def test_accepted_phase_label_cannot_bypass_required_message_envelope() -> None:
    forged = "tekst bez koperty"
    digest = sha256_host_visible_text(forged)
    payload = {
        "final_visible_text": forged,
        "chatgpt_host_bridge": {
            "phase": "host_visible_reply_recorded",
            "turn_id": "turn-1",
            "trace_id": "trace-1",
            "timestamp_header": "🕒 2026-09-10 23:50:00",
            "state_emoticon": "🛠️",
            "author_label": "Łatka",
            "author_source": "jazn_runtime",
        },
        "host_visible_finalization": {
            "accepted": True,
            "final_visible_text": forged,
            "final_text_sha256": digest,
            "turn_id": "turn-1",
            "trace_id": "trace-1",
        },
        "host_visible_reply_capture": {
            "turn_id": "turn-1",
            "trace_id": "trace-1",
            "final_visible_text": forged,
            "final_text_sha256": digest,
            "envelope_present_in_final": False,
        },
    }
    assert chatgpt_result_has_displayable_host_final(payload) is False


def test_complete_captured_message_envelope_is_required_for_display_exact() -> None:
    final = "🕒 2026-09-10 23:50:00\n🛠️ Łatka\n\nDobry wieczór"
    digest = sha256_host_visible_text(final)
    payload = {
        "final_visible_text": final,
        "chatgpt_host_bridge": {
            "phase": "host_visible_reply_recorded",
            "turn_id": "turn-2",
            "trace_id": "trace-2",
            "timestamp_header": "🕒 2026-09-10 23:50:00",
            "state_emoticon": "🛠️",
            "author_label": "Łatka",
            "author_source": "jazn_runtime",
        },
        "host_visible_finalization": {
            "accepted": True,
            "final_visible_text": final,
            "final_text_sha256": digest,
            "turn_id": "turn-2",
            "trace_id": "trace-2",
        },
        "host_visible_reply_capture": {
            "turn_id": "turn-2",
            "trace_id": "trace-2",
            "timestamp_header": "🕒 2026-09-10 23:50:00",
            "state_emoticon": "🛠️",
            "author_label": "Łatka",
            "author_source": "jazn_runtime",
            "final_visible_text": final,
            "final_text_sha256": digest,
            "envelope_present_in_final": True,
        },
    }
    assert chatgpt_result_has_displayable_host_final(payload) is True


def test_active_chatgpt_instructions_fail_closed_without_accepted_visible_final() -> None:
    runbook = _read("AGENTS.chatgpt.md")
    loader = _read("docs/runtime/CHATGPT_PROJECT_INSTRUCTIONS.txt")
    architecture = _read("docs/architecture/MAIN_ENTRYPOINT_AND_PERSISTENT_CHATGPT_BRIDGE.md")
    combined = "\n".join((runbook, loader, architecture))

    assert "daemon_bound_transactional_turns" in combined
    assert "phase_result_ready=true" in combined
    assert "accepted" in combined.lower() and "final_visible_text" in combined
    assert "Żywy PID" in combined or "żywy daemon" in combined
    assert "<state_emoticon> Łatka" in combined
    assert "host_diagnostic" in combined
    assert "długości życia" in combined


def test_machine_readable_contracts_require_accepted_visible_turn() -> None:
    startup = json.loads(_read("latka_jazn/resources/startup_contract.json"))
    self_knowledge = json.loads(
        _read("latka_jazn/resources/canon/LATKA_SELF_KNOWLEDGE_CONTRACT.json")
    )

    assert startup["chatgpt_transport_selection"] == "capability_negotiated"
    assert startup["chatgpt_fallback_transport"] == "daemon_bound_transactional_turns"
    assert startup["chatgpt_pipe_lifetime_is_identity"] is False
    assert startup["accepted_visible_turn_required"] is True
    assert startup["visible_turn_readiness"] == "accepted_final_visible_text_only"
    visible_turn = self_knowledge["answer_contract"]["visible_turn"]
    assert "display_exact" in visible_turn
    assert "final_visible_text" in visible_turn
    assert "host_diagnostic" in visible_turn


