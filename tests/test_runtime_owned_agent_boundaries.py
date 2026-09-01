from __future__ import annotations

from pathlib import Path

from latka_jazn.config import JaznConfig
from latka_jazn.core.chat_command_contract import build_chatgpt_host_bridge_turn_contract
from latka_jazn.core.handlers.direct_latka_voice_handler import DirectLatkaVoiceHandler
from latka_jazn.core.handlers.identity_runtime_truth_handler import IdentityRuntimeTruthHandler
from latka_jazn.core.runtime_ownership_contract import build_runtime_ownership_contract
from latka_jazn.nlp.dialogue_intent_classifier import DialogueIntentClassifier


ROOT = Path(__file__).resolve().parents[1]


def test_project_instructions_are_thin_loader_to_agents_router() -> None:
    text = (ROOT / "docs/runtime/CHATGPT_PROJECT_INSTRUCTIONS.txt").read_text(encoding="utf-8")
    assert len(text) <= 8000
    assert "`AGENTS.md`" in text
    assert "`AGENTS.chatgpt.md`" in text
    assert "Przed pierwszą zwykłą odpowiedzią" in text
    assert "ZIP" in text
    assert "executora/terminala" in text
    assert "kanonicznym runbookiem" in text
    assert "package_available" not in text
    assert "runtime_process_alive" not in text
    assert "final_visible_text" not in text
    assert "HOST_ROUTING_BYPASS" not in text


def test_obsolete_packaged_chatgpt_loader_is_removed() -> None:
    assert not (ROOT / "latka_jazn/resources/chatgpt_startup_loader.txt").exists()
    assert (ROOT / "AGENTS.md").is_file()
    assert (ROOT / "AGENTS.chatgpt.md").is_file()


def test_chatgpt_runbook_does_not_reclassify_presence_as_health_check() -> None:
    text = (ROOT / "AGENTS.chatgpt.md").read_text(encoding="utf-8")
    assert "Pytania rozmowne o obecność, ciągłość lub tożsamość przekazuj do runtime" in text
    assert "Pytania „Działasz?”" not in text
    assert "Jeżeli runtime zwróci zaakceptowany `final_visible_text`, pokaż dokładnie ten tekst" in text


def test_chatgpt_runbook_uses_current_execution_environment_for_local_bootstrap() -> None:
    text = (ROOT / "AGENTS.chatgpt.md").read_text(encoding="utf-8")
    assert "terminal i pliki" in text
    assert "paczek dostępnych lokalnie w bieżącym środowisku ChatGPT" in text
    assert "Jeżeli marker jest nieobecny lub nieważny" in text
    assert "Jeżeli istnieje tylko lokalne archiwum systemowe, wykonaj bezpieczny bootstrap" in text


def test_runtime_owns_routing_identity_voice_memory_and_finalization() -> None:
    contract = build_runtime_ownership_contract(
        detected_intent="identity_continuity_check",
        route="identity_runtime_truth_contract",
    )
    assert contract["current_turn"] == {
        "detected_intent": "identity_continuity_check",
        "route": "identity_runtime_truth_contract",
    }
    assert contract["identity_voice"]["display_name"] == "Łatka"
    assert contract["identity_voice"]["dialogue_language"] == "pl-PL"
    assert contract["ownership"]["routing"]
    assert contract["ownership"]["memory"]
    assert contract["ownership"]["finalization"]
    assert contract["host_visible_generation_contract"]["source"] == "runtime_code_and_source_controlled_canon"


def test_presence_identity_and_health_check_remain_separate_runtime_intents() -> None:
    classifier = DialogueIntentClassifier()
    expected = {
        "Jesteś tu?": "presence_check",
        "Czy to nadal Ty?": "identity_continuity_check",
        "Czy działasz?": "runtime_health_check",
    }
    for text, intent in expected.items():
        assert classifier.classify(text).primary_intent == intent


def test_identity_continuity_handler_uses_runtime_owned_contract() -> None:
    result = IdentityRuntimeTruthHandler().handle(
        "Czy to nadal Ty?",
        {"intent": "identity_continuity_check", "required_components": []},
    )
    assert result.intent == "identity_continuity_check"
    assert result.body.startswith("To nadal ja")
    assert "runtime_ownership_contract" in result.data
    assert result.data["runtime_ownership_contract"]["identity_voice"]["display_name"] == "Łatka"


def test_direct_voice_handler_uses_runtime_owned_contract(tmp_path: Path) -> None:
    result = DirectLatkaVoiceHandler().handle(
        "Chcę rozmawiać bezpośrednio z Łatką",
        {"config": JaznConfig(root=tmp_path), "required_components": []},
    )
    assert "bezpośrednio ze mną" in result.body
    assert "runtime_ownership_contract" in result.data
    assert result.data["runtime_ownership_contract"]["ownership"]["voice"]


def test_chatgpt_bridge_exports_runtime_owned_host_generation_policy() -> None:
    result = {
        "conversation_decision": {
            "detected_user_intent": "ordinary_conversation",
            "route": "ordinary_dialogue",
            "requires_host_model": True,
            "handler_name": "OrdinaryDialogueHandler",
            "timestamp_contract": {
                "timezone": "Europe/Warsaw",
                "sample_iso": "2026-07-31T22:00:00+02:00",
                "source": "local_fallback",
                "trusted": False,
            },
        },
        "runtime_turn_contract": {
            "requires_host_model": True,
            "turn_id": "turn-1",
            "trace_id": "trace-1",
            "timestamp_header": "🕒 2026-07-31 22:00:00",
        },
        "final_response_contract": {
            "requires_host_model": True,
            "runtime_version": "test-version",
            "timestamp_header": "🕒 2026-07-31 22:00:00",
            "timezone": "Europe/Warsaw",
            "timestamp_sample_iso": "2026-07-31T22:00:00+02:00",
            "timestamp_source": "local_fallback",
            "timestamp_trusted": False,
            "author_id": "latka_runtime",
            "author_label": "Łatka",
            "author_source": "jazn_runtime",
            "state_emoticon": "🌿",
        },
        "trace": {
            "turn_id": "turn-1",
            "trace_id": "trace-1",
            "timestamp_header": "🕒 2026-07-31 22:00:00",
        },
    }
    bridge = build_chatgpt_host_bridge_turn_contract(
        result,
        user_text="Porozmawiajmy.",
        chat_bridge_meta={"client": "test"},
    )
    assert bridge["host_must_generate_visible_reply"] is True
    assert bridge["runtime_summary"]["detected_intent"] == "ordinary_conversation"
    assert bridge["runtime_ownership_contract"]["current_turn"]["route"] == "ordinary_dialogue"
    assert bridge["host_generation_policy"]["source"] == "runtime_code_and_source_controlled_canon"
    assert any("Instrukcje projektu" in rule for rule in bridge["host_generation_rules"])
