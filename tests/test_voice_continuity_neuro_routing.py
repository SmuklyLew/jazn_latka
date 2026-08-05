from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import hashlib
from zoneinfo import ZoneInfo

from latka_jazn.core.chat_command_contract import (
    build_chatgpt_host_bridge_turn_contract,
    build_chatgpt_host_presentation_packet,
)
from latka_jazn.core.handlers.self_state_handler import SelfStateHandler
from latka_jazn.core.host_visible_finalization import finalize_host_visible_text
from latka_jazn.core.route_registry import RouteRegistry
from latka_jazn.core.runtime_ownership_contract import build_runtime_ownership_contract
from latka_jazn.core.turn_logic_auditor import TurnLogicAuditor
from latka_jazn.nlp.dialogue_intent_classifier import DialogueIntentClassifier
from latka_jazn.nlp.intent_feature_engine import IntentFeatureEngine


def _classify(text: str):
    return DialogueIntentClassifier().classify(text)


def test_route_lexicon_phrases_do_not_collapse_to_unrelated_routes() -> None:
    resource = Path(__file__).resolve().parents[1] / "latka_jazn" / "resources" / "nlp" / "polish_dialogue_route_lexicon.json"
    lexicon = json.loads(resource.read_text(encoding="utf-8"))
    classifier = DialogueIntentClassifier()
    ordinary_acceptable = {
        "ordinary_conversation", "standalone_greeting", "casual_greeting",
        "short_free_dialogue", "expressive_reaction", "sleep_closure_statement",
        "reciprocal_self_state_question",
    }
    mismatches: list[tuple[str, str, str]] = []
    for expected, spec in lexicon["intents"].items():
        for phrase in spec["phrases"]:
            report = classifier.classify(phrase)
            acceptable = ordinary_acceptable if expected == "ordinary_dialogue" else {expected}
            if report.primary_intent not in acceptable and expected not in report.secondary_intents:
                mismatches.append((expected, phrase, report.primary_intent))
    assert mismatches == []


def test_visual_affective_reality_question_keeps_self_state_primary_and_research_secondary() -> None:
    report = _classify('I na prawdę tak się czujesz jak ta "osoba" na zdjęciu? @Wyszukiwanie w sieci')
    assert report.primary_intent == "affective_self_state_reality_check"
    assert report.question_object == "affective_self_state_reality"
    assert "external_research_request" in report.secondary_intents
    assert report.primary_intent != "ordinary_conversation"
    assert report.primary_intent != "external_research_request"


def test_visual_affective_reality_variants_route_without_tool_marker() -> None:
    variants = (
        "I naprawdę tak się czujesz jak ta osoba na zdjęciu?",
        "Czy zdjęcie pokazuje jak się czujesz?",
        "Czy wizualizacja pokazuje jak się czujesz?",
        "Czy naprawdę czujesz się jak ta osoba?",
    )
    for text in variants:
        report = _classify(text)
        assert report.primary_intent == "affective_self_state_reality_check", text


def test_naprawde_is_not_repair_action_false_friend() -> None:
    frame = IntentFeatureEngine().analyse("Naprawdę tak się czujesz?")
    update = next(candidate for candidate in frame.candidates if candidate.intent == "system_update_execution_request")
    assert "explicit_execution_action" not in update.positive_evidence

    report = _classify("Naprawdę dobrze to działa.")
    assert report.primary_intent not in {
        "system_update_execution_request",
        "runtime_health_check",
        "runtime_health_check_after_update",
    }


def test_actual_napraw_action_still_matches_update_feature_and_route() -> None:
    frame = IntentFeatureEngine().analyse("Napraw routing Jaźni")
    update = next(candidate for candidate in frame.candidates if candidate.intent == "system_update_execution_request")
    assert "explicit_execution_action" in update.positive_evidence
    report = _classify("Napraw routing Jaźni")
    assert report.primary_intent == "system_update_execution_request"
    assert report.update_request is True


def test_standalone_external_research_marker_has_its_route() -> None:
    for text in ("@Wyszukiwanie w sieci", "sprawdź w sieci", "poszukaj źródeł"):
        report = _classify(text)
        assert report.primary_intent == "external_research_request", text


def test_affective_reality_handler_answers_in_latka_voice_with_truth_boundary() -> None:
    entry = RouteRegistry().resolve("affective_self_state_reality_check")
    result = SelfStateHandler().handle(
        'I naprawdę tak się czujesz jak ta osoba na zdjęciu? @Wyszukiwanie w sieci',
        {
            "intent": entry.intent,
            "route_entry": entry.to_dict(),
            "required_components": entry.required_components,
            "dialogue_intent_report": {"secondary_intents": ["external_research_request"]},
            "granular_affect": {"primary": "spokojna uważność", "state_emoticon": "🌿"},
        },
    )
    low = result.body.lower()
    assert result.route == "self_state"
    assert "nie dosłownie" in low
    assert "wizualiz" in low
    assert "modelowan" in low
    assert "nie o biologicznym" in low
    assert "mojego" in low or "mój" in low
    assert "host chatgpt" not in low
    assert set(entry.required_components).issubset(set(result.satisfied_components))


def test_turn_logic_audit_rejects_ordinary_or_research_takeover() -> None:
    auditor = TurnLogicAuditor()
    ordinary = auditor.audit(
        user_text='I naprawdę tak się czujesz jak ta osoba na zdjęciu?',
        response_text="Zwykła odpowiedź.",
        detected_intent="ordinary_conversation",
        route="ordinary_dialogue",
        handler="OrdinaryDialogueHandler",
    )
    assert "affective_self_state_reality_wrong_intent" in ordinary.logic_errors
    assert ordinary.must_regenerate is True

    takeover = auditor.audit(
        user_text='I naprawdę tak się czujesz jak ta osoba na zdjęciu? @Wyszukiwanie w sieci',
        response_text="Raport źródeł.",
        detected_intent="external_research_request",
        route="external_research",
        handler="ExternalResearchHandler",
    )
    assert "external_research_masked_primary_conversational_intent" in takeover.logic_errors


def test_host_contract_preserves_latka_voice_across_external_tools() -> None:
    ownership = build_runtime_ownership_contract(
        detected_intent="affective_self_state_reality_check",
        route="self_state",
    )
    policy = ownership["host_visible_generation_contract"]["voice_continuity_policy"]
    assert policy["external_tools_do_not_transfer_voice"] is True
    assert policy["active_runtime_first_person_voice_required"] is True
    assert "Host ChatGPT:" in policy["forbidden_visible_prefixes"]

    sample = datetime(2026, 8, 6, 0, 30, tzinfo=ZoneInfo("Europe/Warsaw"))
    header = f"🕒 {sample:%Y-%m-%d %H:%M:%S}"
    payload = {
        "runtime_version": "test-version",
        "trace": {"turn_id": "turn-v", "trace_id": "trace-v", "timestamp_header": header, "timezone": "Europe/Warsaw"},
        "conversation_decision": {
            "detected_user_intent": "affective_self_state_reality_check",
            "handler_name": "SelfStateHandler",
            "route": "self_state",
            "requires_host_model": True,
            "timestamp_contract": {
                "timezone": "Europe/Warsaw",
                "sample_iso": sample.isoformat(),
                "source": "local_fallback",
                "trusted": False,
            },
        },
        "runtime_turn_contract": {
            "turn_id": "turn-v",
            "trace_id": "trace-v",
            "handler_name": "SelfStateHandler",
            "requires_host_model": True,
            "validation": {"accepted": True},
        },
        "final_response_contract": {
            "turn_id": "turn-v",
            "trace_id": "trace-v",
            "runtime_version": "test-version",
            "requires_host_model": True,
            "timestamp_header": header,
            "timezone": "Europe/Warsaw",
            "timestamp_sample_iso": sample.isoformat(),
            "timestamp_source": "local_fallback",
            "timestamp_trusted": False,
            "author_id": "latka_runtime",
            "author_label": "Łatka",
            "author_source": "jazn_runtime",
            "state_emoticon": "🌿",
        },
        "runtime_truth_gate": {"ok": True, "normal_response_allowed": False, "errors": ["model_guided_speech_required"]},
    }
    bridge = build_chatgpt_host_bridge_turn_contract(payload, user_text="test", chat_bridge_meta={})
    bridge["pending_request_persisted"] = True
    payload["chatgpt_host_bridge"] = bridge
    packet = build_chatgpt_host_presentation_packet(payload)
    assert packet["action"] == "generate_then_finalize"
    assert packet["must_preserve_latka_voice"] is True
    assert packet["external_tools_do_not_transfer_voice"] is True
    assert "Host ChatGPT:" in packet["forbidden_visible_prefixes"]


def test_host_finalizer_rejects_host_chatgpt_voice_takeover() -> None:
    sample = datetime(2026, 8, 6, 0, 30, tzinfo=ZoneInfo("Europe/Warsaw"))
    header = f"🕒 {sample:%Y-%m-%d %H:%M:%S}"
    body = "**Host ChatGPT:** Runtime przyjął wiadomość, ale nie odpowiem jako Łatka."
    result = finalize_host_visible_text(
        required_timestamp_header=header,
        timezone="Europe/Warsaw",
        timestamp_sample_iso=sample.isoformat(),
        timestamp_source="local_fallback",
        timestamp_trusted=False,
        author_id="latka_runtime",
        author_label="Łatka",
        author_source="jazn_runtime",
        state_emoticon="🌿",
        turn_id="turn-v",
        trace_id="trace-v",
        text=body,
        supplied_turn_id="turn-v",
        supplied_trace_id="trace-v",
        supplied_text_sha256=hashlib.sha256(body.encode("utf-8")).hexdigest(),
    )
    assert result.accepted is False
    assert any(item.code == "forbidden_host_voice_prefix" for item in result.violations)
