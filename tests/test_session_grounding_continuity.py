import pytest

from latka_jazn.core.conversation_state_store import ConversationStateStore
from latka_jazn.core.memory_intent_contract import analyze_memory_intent, is_session_dialogue_reference
from latka_jazn.core.runtime_answer_validator import RuntimeAnswerValidator
from latka_jazn.core.turn_response_policy import TurnResponsePolicy


@pytest.mark.parametrize("question", [
    "Jaką nazwę wcześniej podałem?",
    "Który termin wcześniej zaproponowałaś?",
])
def test_natural_session_reference(question):
    assert is_session_dialogue_reference(question)
    assert not is_session_dialogue_reference(question + " Chodzi o inną sesję.")


def test_conditional_absence_is_not_a_recall_prohibition():
    question = "Jaką nazwę wcześniej podałem? Jeżeli nie pamiętasz, powiedz NIE PAMIĘTAM."
    assert not analyze_memory_intent(question).negated_recall
    assert analyze_memory_intent("Nie przypominaj mi tego.").negated_recall


def test_session_permission_is_scoped():
    policy = TurnResponsePolicy.build(intent="contextual_continuation_question", route="ordinary_dialogue")
    assert policy.to_dict().get("allow_verified_session_history") is True
    assert not policy.allow_memory_content
    assert not policy.allow_previous_turn_carryover


@pytest.mark.parametrize("candidate", ["NIE PAMIĘTAM", "Nazwa to Wega."])
def test_validator_rejects_false_recall_and_false_absence(tmp_path, candidate):
    store = ConversationStateStore(tmp_path)
    assert store.append_finalized_turn(session_id="s", turn_id="t", trace_id="tr",
        user_text="Nazwa to Mira.", assistant_text="Dobrze.", source="runtime")["ok"]
    result = RuntimeAnswerValidator().validate(user_text="Jaką nazwę wcześniej podałem?",
        body=candidate, route="ordinary_dialogue", detected_intent="contextual_continuation_question",
        conversation_history=store.load_context_projection("s"))
    assert not result.accepted


def test_integrity_role_conflicts_correction_and_reopen(tmp_path):
    from latka_jazn.core.session_fact import fact_request

    store = ConversationStateStore(tmp_path)
    def save(turn, user, assistant):
        assert store.append_finalized_turn(session_id="a", turn_id=turn, trace_id="trace-" + turn,
            user_text=user, assistant_text=assistant, source="runtime")["ok"]

    save("one", "Nazwa to Mira.", "Proponuję zielony szlak.")
    query = fact_request("Jaką nazwę wcześniej podałem?")
    proposal = fact_request("Co wcześniej zaproponowałaś?")
    assert query and proposal
    assert store.lookup_session_fact("a", proposal)["text"] == "zielony szlak"
    assert store.lookup_session_fact("b", query)["status"] == "not_found"
    save("two", "Nazwa to Jodła.", "Dobrze.")
    assert store.lookup_session_fact("a", query)["status"] == "ambiguous"
    save("three", "Poprawka: nazwa to Sokół.", "Nazwa to Mira.")
    reopened = ConversationStateStore(tmp_path)
    result = reopened.lookup_session_fact("a", query)
    assert result["text"] == "Sokół" and result["turn_id"] == "three"
    assert len(result["record_sha256"]) == 64
    path = reopened._turn_path("a", "three")
    path.write_text(path.read_text(encoding="utf-8").replace("Sokół", "Mira"), encoding="utf-8")
    assert reopened.lookup_session_fact("a", query)["status"] == "integrity_error"


def test_accepted_fact_uses_rule_handler_and_is_persisted(tmp_path):
    from latka_jazn.config import JaznConfig
    from latka_jazn.core.conversation_runner import ConversationRunner

    cfg = JaznConfig(root=tmp_path, memory_mode="off")
    store = ConversationStateStore(tmp_path)
    assert store.append_finalized_turn(session_id="grounded", turn_id="one", trace_id="trace",
        user_text="Mój numer projektu to 47.", assistant_text="Dobrze.", source="test")["ok"]
    runner = ConversationRunner(cfg, session_id="grounded")
    try:
        result = runner.process_user_text("Przypomnij mi numer projektu z tej rozmowy.")
    finally:
        runner.close()
    assert result["runtime_truth_gate"]["ok"], result["runtime_truth_gate"]
    decision = result["conversation_decision"]
    assert decision["body"] == "47"
    assert decision["fallback_classification"] == "rule_handler_response"
    assert decision["model_generated"] is False
    assert result["canonical_persistence_ok"]
    assert store.load_context_projection("grounded")["total_turn_count"] == 2



def test_contextual_compilation_preserves_older_relevant_turn():
    from latka_jazn.core.local_model_context_compiler import compile_local_model_context

    turns = [{"turn_id": str(i), "trace_id": str(i), "accepted_at_utc": "2026-11-24",
              "user_text": text, "assistant_text": "Rozumiem."}
             for i, text in enumerate(["Projekt Orion", "Spacer", "Pogoda", "Powrót"])]
    history = {"turns": turns, "source_of_truth": "workspace_runtime/conversation_state per-turn accepted records"}
    compiled = compile_local_model_context({"conversation_history": history,
        "detected_intent": "contextual_continuation_question"}, user_text="Co ustaliliśmy dla projektu Orion?")
    assert [turn["turn_id"] for turn in compiled.context["conversation_history"]["turns"]] == ["0", "2", "3"]
