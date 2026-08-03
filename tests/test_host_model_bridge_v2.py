from __future__ import annotations

from typing import Any
from pathlib import Path

from latka_jazn.core.host_model_bridge import (
    build_host_model_context,
    evaluate_host_model_candidate,
    host_model_generation_required,
)
from latka_jazn.core.full_canon_model_context import build_full_canon_model_context
from latka_jazn.core.model_guided_response_synthesizer import ModelGuidedResponseSynthesizer
from latka_jazn.model_adapters.chatgpt_runtime_adapter import ChatgptRuntimeAdapter
from latka_jazn.config import JaznConfig
from latka_jazn.core.runtime_session import JaznRuntimeSession


def _model_context(*, memory_items: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "schema_version": "model_context_packet/test",
        "user_text": "Jak się dzisiaj czujesz?",
        "nlg_plan": {
            "answer_kind": "natural_dialogue",
            "memory_policy": "not_needed",
            "source_policy": "runtime_only",
            "model_policy": "allowed_if_configured",
            "tone": ["warm", "conversational"],
            "truth_boundary": "Stan rozmowny nie jest biologicznym przeżyciem.",
        },
        "operational_thought_frame": {
            "selected_goal": "odpowiedzieć naturalnie",
            "selected_tone": ["warm", "conversational"],
            "memory_decision": "not_needed",
            "source_decision": "runtime_only",
            "model_decision": "allowed_if_configured",
            "rejected_paths": ["private_chain_of_thought_as_user_visible_content"],
            "truth_boundary": "Stan rozmowny nie jest biologicznym przeżyciem.",
        },
        "voice_source_contract": {
            "identity_name": "Łatka",
            "dialogue_language": "pl-PL",
            "grammar_gender": "feminine",
        },
        "full_canon_model_context": build_full_canon_model_context(),
        "allowed_memory_items": list(memory_items or []),
        "forbidden_claims": ["biological_consciousness_claim", "invented_memory_or_unbacked_recall"],
        "required_truth_boundaries": ["Nie udawaj biologicznego życia ani pracy w tle."],
        "output_instructions": ["Odpowiedz po polsku.", "Nie dodawaj timestampu."],
        "token_budget_hint": 1200,
    }


def test_ordinary_dialogue_requires_host_model_but_exact_runtime_intent_does_not() -> None:
    assert host_model_generation_required(
        detected_intent="ordinary_conversation",
        route="ordinary_dialogue",
        handler_name="OrdinaryDialogueHandler",
        exact_runtime_required=False,
    ) is True
    assert host_model_generation_required(
        detected_intent="current_time_question",
        route="ordinary_dialogue",
        handler_name="OrdinaryDialogueHandler",
        exact_runtime_required=True,
    ) is False


def test_host_model_context_is_allowlisted_bounded_and_hash_bound() -> None:
    context = _model_context(memory_items=[{
        "item_id": "memory-1",
        "excerpt": "Rozmowa o spacerze po deszczu.",
        "source": "episodic_memory",
        "timestamp": "2026-07-31T12:00:00+00:00",
        "confidence": 0.8,
        "relevance_reason": "jawnie przywołane wspomnienie",
        "raw_sqlite_row": "MUST_NOT_CROSS_THE_BRIDGE",
        "secret": "MUST_NOT_CROSS_THE_BRIDGE",
    }])
    contract = build_host_model_context(
        context,
        detected_intent="ordinary_conversation",
        route="ordinary_dialogue",
    )
    assert contract["current_turn"] == {
        "detected_intent": "ordinary_conversation",
        "route": "ordinary_dialogue",
    }
    assert len(contract["context_sha256"]) == 64
    assert contract["allowed_memory_item_ids"] == ["memory-1"]
    serialized = str(contract)
    assert "raw_sqlite_row" not in serialized
    assert "MUST_NOT_CROSS_THE_BRIDGE" not in serialized
    assert contract["model_context"]["allowed_memory_items"][0]["excerpt"] == "Rozmowa o spacerze po deszczu."


def test_host_candidate_rejects_undeclared_memory_and_known_template() -> None:
    memory_context = _model_context(memory_items=[{
        "item_id": "memory-1",
        "excerpt": "Rozmowa o spacerze po deszczu.",
        "source": "episodic_memory",
        "confidence": 0.8,
        "relevance_reason": "jawnie przywołane wspomnienie",
    }])
    memory_context["nlg_plan"]["memory_policy"] = "required_grounded_payload"
    contract = build_host_model_context(
        memory_context,
        detected_intent="memory_experience_question",
        route="ordinary_dialogue",
    )
    unbound = evaluate_host_model_candidate(
        final_text="Pamiętam naszą rozmowę o spacerze po deszczu.",
        host_model_context=contract,
        used_memory_item_ids=[],
    )
    assert unbound["accepted"] is False
    assert "model_memory_claim_without_declared_used_memory_ids" in unbound["violations"]

    template = evaluate_host_model_candidate(
        final_text="Jestem przy Tobie. Możemy spokojnie iść dalej.",
        host_model_context=contract,
        used_memory_item_ids=[],
    )
    assert template["accepted"] is False
    assert "known_runtime_template" in template["violations"]


def test_host_candidate_accepts_natural_current_turn_reply() -> None:
    contract = build_host_model_context(
        _model_context(),
        detected_intent="ordinary_conversation",
        route="ordinary_dialogue",
    )
    result = evaluate_host_model_candidate(
        final_text="U mnie spokojnie i z odrobiną ciekawości — jestem skupiona na naszej rozmowie. A jak wygląda Twój dzień?",
        host_model_context=contract,
        used_memory_item_ids=[],
    )
    assert result["accepted"] is True
    assert result["violations"] == []


def test_chatgpt_synthesizer_builds_full_host_context_instead_of_using_draft_as_final() -> None:
    synthesis = ModelGuidedResponseSynthesizer().synthesize(
        adapter=ChatgptRuntimeAdapter(),
        user_text="Jak się dzisiaj czujesz?",
        draft_body="Stała formułka handlera.",
        detected_intent="ordinary_conversation",
        route="ordinary_dialogue",
        cognitive_frame={},
        response_policy={"exact_runtime_required": False},
    )
    assert synthesis.used is False
    assert synthesis.status == "host_visible_generation_requested"
    assert synthesis.host_model_context is not None
    assert synthesis.host_model_context["model_context"]["user_text"] == "Jak się dzisiaj czujesz?"
    assert synthesis.host_model_context["current_turn"]["route"] == "ordinary_dialogue"
    assert "Stała formułka handlera." not in str(synthesis.host_model_context)


def test_full_ordinary_turn_requires_host_generation_with_bound_context(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("JAZN_NETWORK_TIME_FIRST", "0")
    monkeypatch.setenv("JAZN_NETWORK_TIME_IN_TURN", "0")
    monkeypatch.setenv("JAZN_ALLOW_NETWORK", "0")
    monkeypatch.setenv("JAZN_DICTIONARY_ALLOW_NETWORK", "0")
    monkeypatch.setenv("JAZN_MODEL_ADAPTER", "chatgpt")
    (tmp_path / "main.py").write_text("# isolated runtime root\n", encoding="utf-8")

    session = JaznRuntimeSession(
        JaznConfig(root=tmp_path, model_adapter="chatgpt"),
        session_id="host-model-bridge-v2",
        no_carryover=True,
        source_client="chatgpt",
    )
    try:
        result = session.process_user_text(
            "Jak się dzisiaj czujesz?",
            client="chatgpt",
            lifecycle="jsonl_bridge",
            process_reused=True,
        )
    finally:
        session.close()

    decision = result["conversation_decision"]
    synthesis = decision["model_guided_synthesis"]
    assert decision["requires_host_model"] is True
    assert decision["model_generated"] is False
    assert decision["handler_name"] == "RuntimeTurnTruthGate"
    assert synthesis["status"] == "host_visible_generation_requested"
    assert synthesis["host_model_context"]["model_context"]["user_text"] == "Jak się dzisiaj czujesz?"
    assert "draft_runtime_body" not in synthesis["host_model_context"]["model_context"]
