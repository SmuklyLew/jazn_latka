from __future__ import annotations

from latka_jazn.core.dialogue_task_state import DialogueTaskStateResolver
from latka_jazn.core.route_registry import RouteRegistry
from latka_jazn.core.runtime_session_state import RuntimeSessionState
from latka_jazn.core.turn_context_resolver import TurnContextResolver
from latka_jazn.nlp.dialogue_intent_classifier import DialogueIntentClassifier


def _memory_task() -> dict:
    return DialogueTaskStateResolver.derive_state(
        user_text="Zacznij od najwcześniejszych źródeł i odbuduj chronologicznie Pamiętnik.",
        intent="self_memory_recall_request",
        route="self_memory_recall",
        confidence=0.93,
    ).to_dict()


def test_contextual_execution_inherits_structured_memory_task() -> None:
    resolver = DialogueTaskStateResolver()
    result = resolver.resolve(
        current_text="Zgadzam się z Tobą. Zrób to wszystko sama, czyli zacznij teraz.",
        previous_task_state=_memory_task(),
        previous_user_text="Zacznę od najwcześniejszych źródeł.",
        previous_intent="self_memory_recall_request",
        previous_route="self_memory_recall",
        carryover_allowed=True,
    )
    assert result.inherited is True
    assert result.resolved_intent == "self_memory_recall_request"
    assert result.resolved_route == "self_memory_recall"
    assert result.task_state.execution_status == "in_progress"


def test_classifier_uses_task_state_before_loose_ellipsis() -> None:
    report = DialogueIntentClassifier().classify(
        "Zgadzam się z Tobą. Zrób to wszystko sama, czyli zacznij teraz.",
        previous_text="Zacznę od najwcześniejszych źródeł i zbuduję chronologię.",
        previous_intent="self_memory_recall_request",
        previous_route="self_memory_recall",
        previous_task_state=_memory_task(),
        carryover_allowed=True,
    )
    assert report.primary_intent == "self_memory_recall_request"
    assert report.task_resolution["inherited"] is True


def test_turn_context_allows_natural_execute_directive_for_active_task() -> None:
    result = TurnContextResolver().resolve(
        current_user_text="Zgadzam się z Tobą. Zrób to wszystko sama, czyli zacznij teraz.",
        previous_user_text="Zacznę od najwcześniejszych źródeł.",
        previous_intent="self_memory_recall_request",
        previous_route="self_memory_recall",
        previous_task_state=_memory_task(),
    )
    assert result.carryover_allowed is True
    assert result.previous_context_used is True


def test_explicit_current_turn_status_overrides_previous_task() -> None:
    result = DialogueTaskStateResolver().resolve(
        current_text="Sprawdź status runtime.",
        previous_task_state=_memory_task(),
        previous_intent="self_memory_recall_request",
        previous_route="self_memory_recall",
    )
    assert result.inherited is False


def test_contextual_continuation_has_safe_non_fallback_route_without_task() -> None:
    report = DialogueIntentClassifier().classify(
        "Zrób to teraz",
        previous_text="Porozmawiajmy o czymś bez konkretnego zadania.",
        previous_intent="ordinary_conversation",
        previous_route="ordinary_dialogue",
    )
    assert report.primary_intent == "contextual_continuation_question"
    route = RouteRegistry().resolve(report.primary_intent)
    assert route.route == "ordinary_dialogue"
    assert route.handler_name == "OrdinaryDialogueHandler"


def test_runtime_session_state_roundtrips_task_state() -> None:
    state = RuntimeSessionState.create(session_id="v154-test")
    task = _memory_task()
    state.update(
        user_text="start",
        visible_text="ok",
        intent="self_memory_recall_request",
        route="self_memory_recall",
        task_state=task,
    )
    assert state.to_dict()["task_state"]["active_intent"] == "self_memory_recall_request"
    state.clear_carryover()
    assert state.task_state == {}


def test_engine_current_turn_reasoning_binds_resolved_task_and_lessons() -> None:
    from pathlib import Path
    from types import SimpleNamespace

    from latka_jazn.core.cognitive_runtime_coordinator import CognitiveRuntimeCoordinator
    from latka_jazn.core.engine import JaznEngine
    from latka_jazn.core.operational_learning_memory import OperationalLearningMemory

    engine = JaznEngine.__new__(JaznEngine)
    engine.route_registry = RouteRegistry()
    engine.dialogue_task_state_resolver = DialogueTaskStateResolver()
    engine.cognitive_runtime_coordinator = CognitiveRuntimeCoordinator()
    root = Path(__file__).resolve().parents[1]
    engine.operational_learning_memory = OperationalLearningMemory.from_json_file(
        root / "latka_jazn" / "resources" / "cognition" / "v154_operational_lessons.json"
    )

    frame = {
        "memory_context": {"counts": {"conversation_archive": 2}},
        "memory_recall_contract": {"items": [{"source": "archive"}]},
        "tool_use_decision": {"allowed": False},
    }
    envelope = SimpleNamespace(
        cognitive_frame={"dialogue_intent_classifier": {"primary_intent": "self_memory_recall_request"}}
    )
    decision: dict = {}
    intent_report = {"confidence": 0.95, "task_resolution": {"inherited": True}}

    detected, route, task, _policy = engine._apply_current_dialogue_control(
        text="Zgadzam się z Tobą. Zrób to wszystko sama, czyli zacznij teraz.",
        frame=frame,
        envelope=envelope,
        decision_dict=decision,
        dialogue_intent_report=intent_report,
        previous_task_state=_memory_task(),
        client_context={},
    )

    assert detected == "self_memory_recall_request"
    assert route.route == "self_memory_recall"
    assert task["active"] is True
    assert "bind_active_dialogue_task" in decision["reasoning_plan"]["operational_steps"]
    assert decision["reasoning_plan"]["requires_retrieval"] is True
    assert decision["operational_learning_lessons"]
    assert decision["operational_learning_lessons"][0]["verified"] is True
