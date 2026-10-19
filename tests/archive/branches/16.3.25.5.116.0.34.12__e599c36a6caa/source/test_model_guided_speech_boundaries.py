from __future__ import annotations

from latka_jazn.core.llm_route_resolver import LlmRouteStatus, ROUTE_NULL
from latka_jazn.core.model_guided_speech_runtime import build_model_guided_speech_status


class _MalformedDescriptionAdapter:
    def describe(self) -> object:
        return None


def test_non_object_adapter_description_fails_closed() -> None:
    route = LlmRouteStatus(
        ok=False,
        route_mode="none",
        selected_route=ROUTE_NULL,
        paid_route=False,
        paid_route_allowed=False,
        local={},
        chatgpt_bridge={},
        openai_api={},
        reason="test",
        selected_adapter="null",
    )

    status = build_model_guided_speech_status(
        object(),
        env={"JAZN_MODEL_GUIDED_SPEECH": "1"},
        adapter=_MalformedDescriptionAdapter(),
        llm_route_status=route,
    )

    assert status.ok is False
    assert status.adapter_status == {}
    assert status.can_attempt_model_guided_speech is False
    assert status.can_generate_model_guided_speech is False
