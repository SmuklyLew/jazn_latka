"""Read-only intent, failure-report routing and bounded retry regression."""
from __future__ import annotations

from types import SimpleNamespace
import pytest
from latka_jazn.core.host_finalization_transaction import HostFinalizationPorts, _request_repair_or_reject
from latka_jazn.core.route_registry import RouteRegistry
from latka_jazn.core.runtime_answer_validator import RuntimeAnswerValidator
from latka_jazn.core.turn_response_policy import TurnResponsePolicy
from latka_jazn.nlp.dialogue_intent_classifier import DialogueIntentClassifier
from latka_jazn.nlp.utterance_components import analyse_utterance


@pytest.mark.parametrize(("utterance", "intent", "execution"), [
    ("Jaźń nie działa!", "runtime_failure_report", False),
    ("System Jaźń nie działa.", "runtime_failure_report", False),
    ("Sprawdź teraz, co możemy wiarygodnie naprawić w kodzie źródłowym systemu Jaźni.", "system_diagnostic_question", False),
    ("Zrób audyt co trzeba naprawić w Jaźni.", "self_architecture_audit_request", False),
    ("Nie naprawiaj systemu Jaźni, tylko opisz problem.", "system_diagnostic_question", False),
    ("Napraw teraz kod systemu Jaźni na nowym branchu.", "system_update_execution_request", True),
    ("Przygotuj aktualizację, która dokończy brakujące punkty.", "system_update_execution_request", True),
    ("@GitHub Przygotuj aktualizację systemu Jaźni na nowym branchu.", "system_update_execution_request", True),
])
def test_speech_act_does_not_invent_write_authority(utterance: str, intent: str, execution: bool) -> None:
    report = DialogueIntentClassifier().classify(utterance)
    components = analyse_utterance(utterance)
    assert report.primary_intent == intent
    assert components.explicit_execution is execution
    assert report.update_request is execution
    assert (RouteRegistry().resolve(report.primary_intent).route == "system_update") is execution


def test_infinitive_does_not_match_rights_components() -> None:
    report = analyse_utterance("Sprawdź, co można naprawić w kodzie systemu Jaźni.")
    assert "rights_obligations" not in report.components
    assert report.explicit_execution is False
    assert "rights_obligations" in analyse_utterance("Jakie prawa ma Jaźń?").components


def test_runtime_failure_report_is_natural_and_is_not_auto_diagnostic() -> None:
    entry = RouteRegistry().resolve("runtime_failure_report")
    policy = TurnResponsePolicy.build(intent=entry.intent, route=entry.route)
    assert entry.route == "ordinary_dialogue"
    assert entry.required_components == []
    assert policy.required_components == []
    result = RuntimeAnswerValidator().validate(
        user_text="Jaźń nie działa!",
        body="Rozumiem zgłoszenie, ale nie mogę potwierdzić gotowego runtime bez dowodów bieżącej tury.",
        route=entry.route, detected_intent=entry.intent,
    )
    assert result.accepted, result.to_dict()


@pytest.mark.parametrize("intent", [
    "system_diagnostic_question", "runtime_behavior_diagnostic_request", "system_repair_plan_request",
])
def test_policy_and_validator_share_one_component_source(intent: str) -> None:
    entry = RouteRegistry().resolve(intent)
    policy = TurnResponsePolicy.build(intent=intent, route=entry.route)
    assert policy.required_components == entry.required_components


def test_focused_diagnostic_does_not_demand_implementation_plan() -> None:
    intent = "system_diagnostic_question"
    entry = RouteRegistry().resolve(intent)
    result = RuntimeAnswerValidator().validate(
        user_text="Sprawdź, co nie działa w Jaźni.",
        body="Problem potwierdzony w klasyfikacji zgłoszenia. Źródło: bieżący kod i test regresji.",
        route=entry.route, detected_intent=intent,
    )
    assert result.accepted, result.to_dict()
    assert "target_files" not in entry.required_components
    assert "acceptance_criteria" not in entry.required_components


def test_host_retry_names_trusted_missing_slots_without_replaying_user_text(monkeypatch, tmp_path) -> None:
    from latka_jazn.core import host_finalization_transaction as tx

    def fake_request(root, *, turn_id, reason):
        assert root == tmp_path and turn_id == "turn-01"
        return {
            "binding": {"turn_id": "turn-01", "trace_id": "trace-01", "runtime_version": "test"},
            "generation_context": {"host_generation_context": {}},
            "request_contract_hash": "a" * 64,
            "regeneration_attempts": 1,
            "max_regeneration_attempts": 1,
        }

    monkeypatch.setattr(tx, "request_host_regeneration", fake_request)
    ports = HostFinalizationPorts(
        extract_payload=lambda x: (x, []), presentation=lambda x: {"status": "ready"},
        commit_conversation=lambda **kwargs: {}, commit_session=lambda **kwargs: {},
    )
    result, errors = _request_repair_or_reject(
        config=SimpleNamespace(root=tmp_path), ports=ports,
        pending={"regeneration_attempts": 0, "max_regeneration_attempts": 1},
        reply={"turn_id": "turn-01"}, binding={},
        chat_bridge_meta={}, contract={},
        violation_codes=["missing_required_components_for_intent"],
        error_prefix="host_candidate", finalization_payload=None,
        missing_required_components=["problem", "source_origin", "text with spaces"],
    )
    assert errors == [] and result is not None
    bridge = result["chatgpt_host_bridge"]
    assert bridge["missing_required_components"] == ["problem", "source_origin"]
    assert any("problem, source_origin" in hint for hint in bridge["repair_guidance"])
    assert "user_text" not in bridge
    assert bridge["turn_id"] == "turn-01"
