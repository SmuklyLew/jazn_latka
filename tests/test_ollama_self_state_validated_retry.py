"""V127.19: bounded Ollama self-state retry cannot promote a rejected model candidate."""
from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, cast

import pytest

from latka_jazn.core.handlers.self_state_handler import SelfStateHandler
from latka_jazn.core.model_guided_response_synthesizer import ModelGuidedResponseSynthesizer, ModelGuidedSynthesis
from latka_jazn.core.model_executor_preflight import ModelExecutorPreflight
from latka_jazn.core.recovery_policy import RecoveryPolicy, _validated_self_state_retry
from latka_jazn.core.route_registry import RouteRegistry
from latka_jazn.core.runtime_answer_validator import RuntimeAnswerValidator
from latka_jazn.core.turn_response_policy import TurnResponsePolicy

if TYPE_CHECKING:
    from latka_jazn.core.engine import JaznEngine
    from latka_jazn.core.turn_pipeline_state import TurnPipelineState


MESSAGE = "Cześć Łatko. Rozpoczynamy test rozmowy. Jak się masz?"
INTENT = "self_state_question"


def make_state():
    required = RouteRegistry().required_components_for(INTENT)
    handler = SelfStateHandler().handle(
        MESSAGE,
        {"intent": INTENT, "route_entry": {"route": "self_state"}, "required_components": required},
    )
    return SimpleNamespace(
        request=SimpleNamespace(text=MESSAGE, client_context={}),
        detected_dialogue_intent=INTENT,
        route_entry=SimpleNamespace(route="self_state"),
        handler_result=handler,
        handler_required=required,
        handler_satisfied=set(handler.satisfied_components),
        handler_missing=[],
        turn_response_policy=TurnResponsePolicy.build(intent=INTENT, route="self_state"),
        response_plan=SimpleNamespace(required_points=tuple(required), to_dict=lambda: {"required_points": required}),
        decision=SimpleNamespace(body="Wszystko dobrze."),
        first_validation=SimpleNamespace(
            accepted=False, mismatch_reason="missing_required_components_for_intent",
            missing_required_components=["operational_state", "truth_boundary"],
            required_repair_route="self_state_repair",
        ),
        model_synthesis=ModelGuidedSynthesis(
            True, "Wszystko dobrze.", "completed", "ollama", "gemma3", "candidate",
            [], adapter_response={"status": "completed", "provider": "ollama", "model": "gemma3"},
        ),
        model_executor=ModelExecutorPreflight(
            executor="local_model", available=True, retry_allowed=True,
            adapter_id="local_llm_adapter", provider="ollama", model="gemma3",
            reason="synthetic_local_executor",
        ),
        speech_adapter=object(),
        template_origin={},
        adapter_status={},
        decision_dict={"route": "self_state"},
        frame={},
        turn_context=None,
        preserve_handler_body=False,
    )


def test_original_handler_is_valid_but_unverified_model_sentence_is_not():
    state = make_state()
    validator = RuntimeAnswerValidator()
    assert validator.validate(
        user_text=MESSAGE, body=state.handler_result.body,
        route="self_state", detected_intent=INTENT,
    ).accepted
    invalid = validator.validate(
        user_text=MESSAGE, body=state.decision.body,
        route="self_state", detected_intent=INTENT,
    )
    assert not invalid.accepted
    assert set(invalid.missing_required_components) == {"operational_state", "truth_boundary"}


def test_retry_restores_validated_runtime_handler_and_feedback():
    state = make_state()
    engine = SimpleNamespace(runtime_answer_validator=RuntimeAnswerValidator())
    draft, policy = _validated_self_state_retry(cast('TurnPipelineState', state), cast('JaznEngine', engine))
    assert draft == state.handler_result.body
    assert draft != state.decision.body
    assert policy["retry_validation_feedback"] == {
        "missing_required_components": ["operational_state", "truth_boundary"],
        "repair_route": "self_state_repair",
        "source": "runtime_answer_validator",
    }


def test_retry_refuses_unvalidated_handler_draft():
    state = make_state()
    state.handler_result.body = "Świetnie, świetnie."
    engine = SimpleNamespace(runtime_answer_validator=RuntimeAnswerValidator())
    draft, _ = _validated_self_state_retry(cast('TurnPipelineState', state), cast('JaznEngine', engine))
    assert draft == state.decision.body


def test_repair_instructions_are_allowlisted_not_derived_from_untrusted_text(monkeypatch):
    import latka_jazn.core.model_guided_response_synthesizer as module

    monkeypatch.setattr(module, "build_nlg_plan", lambda **kwargs: {})
    monkeypatch.setattr(module, "build_operational_thought_frame", lambda **kwargs: {})
    monkeypatch.setattr(
        module, "compile_model_context",
        lambda **kwargs: SimpleNamespace(to_dict=lambda: {"output_instructions": ["Odpowiedz po polsku."]}),
    )
    context = ModelGuidedResponseSynthesizer._build_context(
        user_text=MESSAGE, draft_body="U mnie operacyjnie spokojnie.",
        detected_intent=INTENT, route="self_state", cognitive_frame={},
        response_policy={
            "retry_validation_feedback": {
                "source": "runtime_answer_validator",
                "missing_required_components": [
                    "operational_state", "truth_boundary", "UNTRUSTED_INJECTION"
                ],
            }
        },
    )
    output = " ".join(context["output_instructions"])
    assert "stan rozmowny" in output
    assert "biologiczne" in output
    assert "operational_state, truth_boundary" in output
    assert "UNTRUSTED_INJECTION" not in output


@pytest.mark.parametrize("retry_success", [True, False])
def test_bounded_retry_never_accepts_unvalidated_fallback(retry_success):
    state = make_state()
    calls = []

    class StubSynthesizer:
        def synthesize(self, **kwargs):
            calls.append(kwargs)
            if retry_success:
                return ModelGuidedSynthesis(
                    True, state.handler_result.body, "completed", "ollama", "gemma3",
                    "grounded_retry", [],
                    adapter_response={"status": "completed", "provider": "ollama", "model": "gemma3"},
                )
            return ModelGuidedSynthesis(
                False, "Niezweryfikowany fallback", "unavailable", "ollama", "gemma3",
                "rejected_retry", [],
            )

    class Validator(RuntimeAnswerValidator):
        def validate_model_candidate(self, **kwargs):
            return super().validate(
                user_text=kwargs["user_text"], body=kwargs["response"]["text"],
                route=kwargs["route"], detected_intent=kwargs["detected_intent"],
            )

    engine = SimpleNamespace(
        runtime_answer_validator=Validator(),
        model_guided_response_synthesizer=StubSynthesizer(),
        model_adapter=object(),
        guard=SimpleNamespace(enforce=lambda value: value),
        template_registry=SimpleNamespace(classify_body=lambda *args, **kwargs: {}),
        continuity_badge_policy=SimpleNamespace(apply=lambda body, decision: (body, {})),
        _record_model_retry_diagnostic=lambda context: None,
    )
    RecoveryPolicy(cast('JaznEngine', engine)).resolve(cast('TurnPipelineState', state))
    assert len(calls) == 1
    assert calls[0]["draft_body"] == state.handler_result.body
    assert state.decision_dict["model_guided_retry_count"] == 1
    if retry_success:
        assert state.decision_dict["fallback_classification"] == "not_fallback"
        assert state.answer_validation.accepted
        assert state.body == state.handler_result.body
    else:
        assert state.decision_dict["fallback_classification"] == "cannot_answer_directly"
        assert state.decision_dict["handler_name"] == "RuntimeTurnTruthGate"
        assert state.decision_dict["model_generation_required"] is True
        assert state.decision_dict["requires_host_model"] is False
        assert state.body != state.handler_result.body
