from pathlib import Path
import pytest

from latka_jazn.config import JaznConfig
from latka_jazn.core.conversation import ConversationResponder
from latka_jazn.core.handlers.ordinary_dialogue_handler import OrdinaryDialogueHandler
from latka_jazn.core.runtime_composition import RuntimeCompositionRoot
from latka_jazn.core.turn_execution import TurnExecutionContext


@pytest.mark.parametrize("intent,text", [("standalone_greeting", "Hej"), ("short_free_dialogue", "Opowiedz historię"),
                                         ("sleep_closure_statement", "Dobranoc"), ("positive_feedback_current_turn", "Dziękuję")])
def test_ordinary_candidate_is_structured_and_does_not_claim_body_components(intent, text):
    candidate = ConversationResponder.build_candidate(text, classified_intent=intent)
    assert candidate.body == ""
    assert candidate.detected_user_intent == intent
    assert candidate.substantive_remainder == text
    result = OrdinaryDialogueHandler().handle(text, {"intent": intent, "canonical_dialogue_cutover": True,
                                                    "required_components": ["current_turn_reply"]})
    assert result.body == ""
    assert result.satisfied_components == []
    assert result.missing_components == ["current_turn_reply"]
    assert result.data["language_realization_required"] is True
    assert result.generation_mode == "structured_candidate"


def test_canonical_turn_never_calls_legacy_compose_or_ordinary_template(tmp_path: Path, monkeypatch):
    for name in ("JAZN_NETWORK_TIME_FIRST", "JAZN_NETWORK_TIME_IN_TURN", "JAZN_ALLOW_NETWORK", "JAZN_DICTIONARY_ALLOW_NETWORK"):
        monkeypatch.setenv(name, "0")
    monkeypatch.setenv("JAZN_MODEL_ADAPTER", "null")
    monkeypatch.setenv("JAZN_LLM_ROUTE_SKIP_LOCAL_PROBE", "1")
    def forbidden(*args, **kwargs):
        raise AssertionError("legacy dialogue was invoked by the canonical turn")
    monkeypatch.setattr(ConversationResponder, "compose", forbidden)
    monkeypatch.setattr(OrdinaryDialogueHandler, "_natural_body", forbidden)
    root = RuntimeCompositionRoot(JaznConfig(root=tmp_path / "runtime"))
    engine = root.create_engine()
    try:
        context = TurnExecutionContext.create(request_id="cutover", timeout_seconds=90)
        result = engine.process_turn("Hej.", client_context={"_turn_context": context}).to_dict()
        decision = result["conversation_decision"]
        assert decision["dialogue_candidate_source"] == "classified_structured_candidate"
        assert decision["handler_result"]["generation_mode"] == "structured_candidate"
        assert decision["model_generated"] is False
        assert decision["fallback_classification"] == "cannot_answer_directly"
        assert decision["requires_host_model"] is True
        assert decision["origin_truth_valid"] is False
        assert "classified_fallback" in decision["origin_truth_errors"]
        assert result["final_response_contract"]["requires_host_model"] is True
        assert not context._canonical_committed
    finally:
        root.close()
