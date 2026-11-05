from types import SimpleNamespace

import pytest

from latka_jazn.core.handlers.time_awareness_handler import TimeAwarenessHandler
from latka_jazn.core.model_executor_preflight import ModelExecutorPreflight
from latka_jazn.core.model_guided_response_synthesizer import (
    ModelGuidedResponseSynthesizer,
)
from latka_jazn.core.runtime_answer_validator import RuntimeAnswerValidator
from latka_jazn.core.response_generation_mode import build_runtime_provenance
from latka_jazn.core.visible_integrity import evaluate_origin_truth


class FakeClock:
    def __init__(self, trusted):
        self.trusted = trusted

    def now(self, refresh=False):
        return SimpleNamespace(
            trusted=self.trusted,
            source="test_network_time" if self.trusted else "local_os",
        )

    def header(self, sample):
        return "🕒 2026-11-05 04:30:00 Europe/Warsaw"


class ForbiddenModel:
    def describe(self):
        return {
            "name": "offline-ollama-test",
            "provider": "ollama",
            "model": "fixture",
        }

    def generate(self, *args, **kwargs):
        raise AssertionError("Model must not generate runtime clock facts")

    def chat(self, *args, **kwargs):
        raise AssertionError("Model must not generate runtime clock facts")


@pytest.mark.parametrize("trusted", [True, False])
def test_time_question_preserves_runtime_clock(trusted):
    question = "Która jest godzina?"
    handler = TimeAwarenessHandler().handle(
        question,
        {
            "clock": FakeClock(trusted),
            "intent": "time_awareness_question",
            "required_components": [
                "current_time",
                "timezone",
                "source_or_fallback",
                "truth_boundary",
            ],
        },
    )

    output = ModelGuidedResponseSynthesizer().synthesize(
        adapter=ForbiddenModel(),
        user_text=question,
        draft_body=handler.body,
        detected_intent="time_awareness_question",
        route="time_awareness",
        cognitive_frame={},
        response_policy={"exact_runtime_required": False},
        executor_preflight=ModelExecutorPreflight(
            executor="local_model",
            available=True,
            retry_allowed=False,
            adapter_id="offline-ollama-test",
            provider="ollama",
            model="fixture",
            reason="protected_runtime_time_test",
        ),
    )

    assert output.used is False
    assert output.body == handler.body
    assert output.status == "skipped"

    validator = RuntimeAnswerValidator()
    validation = validator.validate(
        user_text=question,
        body=output.body,
        route="time_awareness",
        detected_intent="time_awareness_question",
    )
    assert validation.accepted, validation.to_dict()

    header = "🕒 2026-11-05 04:30:00 Europe/Warsaw"
    visible = f"{header}\nŁatka\n\n{output.body}"

    provenance = build_runtime_provenance(
        body=output.body,
        route="time_awareness",
        detected_intent="time_awareness_question",
        handler_name=handler.handler_name,
        fallback_classification="rule_handler_response",
        source_origin_detail=handler.source_origin_detail,
    ).with_visible_text(visible).to_dict()

    truth, errors = evaluate_origin_truth(
        {
            "fallback_classification": "rule_handler_response",
            "handler_result": handler.to_dict(),
            "handler_name": handler.handler_name,
            "final_answer_validation": validation.to_dict(),
            "runtime_provenance": provenance,
        },
        body=output.body,
        final_visible_text=visible,
        timestamp_header=header,
    )
    assert truth, errors


def test_answer_without_runtime_time_is_rejected():
    validation = RuntimeAnswerValidator().validate(
        user_text="Która jest godzina?",
        body="Cześć, miło Cię widzieć.",
        route="time_awareness",
        detected_intent="time_awareness_question",
    )
    assert not validation.accepted


def test_ordinary_greeting_remains_model_eligible():
    assert "casual_greeting" not in ModelGuidedResponseSynthesizer.PROTECTED_INTENTS
