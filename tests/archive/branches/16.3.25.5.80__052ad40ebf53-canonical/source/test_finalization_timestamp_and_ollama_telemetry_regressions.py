from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json

from latka_jazn.core.cognitive_turn_envelope import CognitiveTurnEnvelope
from latka_jazn.core.model_executor_preflight import resolve_model_executor
from latka_jazn.core.model_guided_response_synthesizer import (
    ModelGuidedResponseSynthesizer,
)
from latka_jazn.core.response_candidate import CandidateEvaluation, ResponseCandidate
from latka_jazn.core.response_candidate_generator import generate_response_candidates
from latka_jazn.model_adapters.base import ModelAdapterRequest, ModelAdapterResponse
from latka_jazn.model_adapters.local_llm_adapter import LocalLlmAdapter
from latka_jazn.version import PACKAGE_VERSION


def _timestamp_contract(sample: datetime) -> dict:
    local = sample.astimezone()
    return {
        "sample_iso": sample.isoformat(),
        "source": "local_fallback",
        "trusted": False,
        "timestamp_header": f"🕒 {local:%Y-%m-%d %H:%M:%S}",
        "timezone": "Europe/Warsaw",
        "max_age_seconds": 120,
    }


def test_envelope_refreshes_all_finalization_timestamp_views() -> None:
    started = datetime.now(timezone.utc) - timedelta(minutes=3)
    finalized = datetime.now(timezone.utc)
    started_contract = _timestamp_contract(started)
    final_contract = _timestamp_contract(finalized)
    started_header = started_contract["timestamp_header"]
    final_header = final_contract["timestamp_header"]

    frame = {
        "runtime_version": PACKAGE_VERSION,
        "timestamp": started_header,
        "timestamp_contract": started_contract,
        "turn_id": "turn-1",
        "trace_id": "trace-1",
        "turn_trace": {
            "turn_id": "turn-1",
            "trace_id": "trace-1",
            "timestamp_header": started_header,
            "timezone": "Europe/Warsaw",
            "runtime_mode": "cognitive_frame",
            "client": "test",
            "lifecycle": "one_shot",
        },
        "response_format": {
            "timestamp_prefix": started_header,
            "current_timestamp": started_header,
            "example_start": f"{started_header} ",
            "timezone": "Europe/Warsaw",
        },
    }
    envelope = CognitiveTurnEnvelope.from_cognitive_frame(
        frame,
        user_text="test",
        client_context={"client": "test"},
    )
    envelope.attach_conversation_decision(
        {"timestamp_contract": started_contract}
    )

    refresh = envelope.refresh_finalization_timestamp(
        timestamp_header=final_header,
        timestamp_contract=final_contract,
    )

    assert refresh["turn_started_timestamp_header"] == started_header
    assert refresh["turn_started_timestamp_contract"]["sample_iso"] == started.isoformat()
    assert refresh["finalization_timestamp_header"] == final_header
    assert envelope.trace.timestamp_header == final_header
    assert envelope.cognitive_frame["timestamp"] == final_header
    assert envelope.cognitive_frame["turn_trace"]["timestamp_header"] == final_header
    assert envelope.cognitive_frame["response_format"]["timestamp_prefix"] == final_header
    assert envelope.cognitive_frame["response_format"]["current_timestamp"] == final_header
    assert envelope.cognitive_frame["timestamp_contract"]["sample_iso"] == finalized.isoformat()
    assert envelope.cognitive_frame["turn_started_timestamp_contract"]["sample_iso"] == started.isoformat()
    assert envelope.conversation_decision["timestamp_contract"]["sample_iso"] == finalized.isoformat()
    assert envelope.conversation_decision["turn_started_timestamp_contract"]["sample_iso"] == started.isoformat()


def test_local_adapter_records_timeout_attempt_in_transport(monkeypatch) -> None:
    def _timeout(*args, **kwargs):
        raise TimeoutError("timed out")

    monkeypatch.setattr(
        "latka_jazn.model_adapters.local_llm_adapter.urlopen",
        _timeout,
    )
    adapter = LocalLlmAdapter(
        model="gemma3:latest",
        timeout_seconds=0.01,
    )

    response = adapter.generate(
        ModelAdapterRequest(
            prompt="Odpowiedz krótko.",
            system_context={"route": "ordinary_dialogue"},
        )
    )

    assert response.status == "timeout"
    assert response.generated is False
    attempts = response.transport["attempts"]
    assert len(attempts) == 1
    attempt = attempts[0]
    assert attempt["status"] == "timeout"
    assert attempt["error_code"] == "model_request_timeout"
    assert attempt["timed_out"] is True
    assert attempt["wall_clock_duration_ms"] >= 0
    assert attempt["system_prompt_chars"] > 0
    assert attempt["user_prompt_chars"] == len("Odpowiedz krótko.")
    assert attempt["request_bytes"] > attempt["system_prompt_chars"]


class _JsonResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def read(self) -> bytes:
        return self._payload


def test_local_adapter_keeps_ollama_duration_metrics(monkeypatch) -> None:
    payload = {
        "model": "gemma3:latest",
        "message": {"content": "Rozumiem."},
        "done": True,
        "done_reason": "stop",
        "total_duration": 100,
        "load_duration": 20,
        "prompt_eval_duration": 30,
        "eval_duration": 40,
        "prompt_eval_count": 8195,
        "eval_count": 4,
    }
    monkeypatch.setattr(
        "latka_jazn.model_adapters.local_llm_adapter.urlopen",
        lambda *args, **kwargs: _JsonResponse(payload),
    )
    adapter = LocalLlmAdapter(model="gemma3:latest")

    response = adapter.generate(
        ModelAdapterRequest(
            prompt="Odpowiedz jednym zdaniem.",
            system_context={"route": "ordinary_dialogue"},
        )
    )

    assert response.status == "completed"
    attempt = response.transport["attempts"][0]
    assert attempt["prompt_eval_duration"] == 30
    assert attempt["eval_duration"] == 40
    assert attempt["prompt_eval_count"] == 8195
    assert attempt["eval_count"] == 4
    assert attempt["wall_clock_duration_ms"] >= 0


class _FailedAdapter:
    def describe(self) -> dict:
        return {
            "status": "configured",
            "adapter_id": "local_llm_adapter",
            "provider": "ollama",
            "model": "gemma3:latest",
            "configured": True,
            "can_attempt_model_guided_speech": True,
            "can_generate_model_guided_speech": False,
        }

    def generate(self, request: ModelAdapterRequest) -> ModelAdapterResponse:
        return ModelAdapterResponse(
            text="",
            provider="ollama",
            model="gemma3:latest",
            status="timeout",
            adapter_id="local_llm_adapter",
            endpoint_used="/api/chat",
            transport={
                "attempts": [
                    {
                        "status": "timeout",
                        "timed_out": True,
                        "wall_clock_duration_ms": 45000.0,
                    }
                ]
            },
        )


def test_runtime_fallback_candidate_preserves_failed_adapter_response() -> None:
    candidates = generate_response_candidates(
        adapter=_FailedAdapter(),
        nlg_plan={
            "answer_kind": "natural_dialogue",
            "detected_intent": "ordinary_conversation",
            "route": "ordinary_dialogue",
        },
        model_context={
            "user_message": "Test",
            "detected_intent": "ordinary_conversation",
            "route": "ordinary_dialogue",
        },
        fallback_body="Fallback runtime.",
    )

    assert len(candidates) == 1
    fallback = candidates[0]
    assert fallback.source == "runtime_fallback"
    assert fallback.adapter_response["status"] == "timeout"
    assert fallback.adapter_response["transport"]["attempts"][0]["timed_out"] is True
    assert fallback.endpoint_used == "/api/chat"


class _ConfiguredAdapter:
    def describe(self) -> dict:
        return {
            "status": "configured",
            "adapter_id": "local_llm_adapter",
            "provider": "ollama",
            "model": "gemma3:latest",
            "configured": True,
            "can_attempt_model_guided_speech": True,
            "can_generate_model_guided_speech": False,
        }


def test_synthesizer_exposes_fallback_adapter_diagnostics(monkeypatch) -> None:
    diagnostic = {
        "status": "timeout",
        "transport": {"attempts": [{"timed_out": True}]},
    }
    candidate = ResponseCandidate(
        candidate_id="runtime_fallback",
        text="Fallback runtime.",
        source="runtime_fallback",
        provider="jazn_runtime",
        model="runtime",
        status="available",
        used_memory_item_ids=[],
        generation_reason="fallback_runtime_always_available",
        endpoint_used="/api/chat",
        adapter_response=diagnostic,
    )
    evaluation = CandidateEvaluation(
        candidate_id="runtime_fallback",
        accepted=True,
        score=0.5,
        reasons=["runtime_fallback"],
        violations=[],
        requires_repair=False,
    )

    monkeypatch.setattr(
        ModelGuidedResponseSynthesizer,
        "_build_context",
        staticmethod(lambda **kwargs: {"nlg_plan": {}, "allowed_memory_items": []}),
    )
    monkeypatch.setattr(
        "latka_jazn.core.model_guided_response_synthesizer.generate_response_candidates",
        lambda **kwargs: [candidate],
    )
    monkeypatch.setattr(
        "latka_jazn.core.model_guided_response_synthesizer.evaluate_response_candidate",
        lambda **kwargs: evaluation,
    )
    monkeypatch.setattr(
        "latka_jazn.core.model_guided_response_synthesizer.select_best_candidate",
        lambda candidates, evaluations: candidates[0],
    )

    adapter = _ConfiguredAdapter()
    result = ModelGuidedResponseSynthesizer().synthesize(
        adapter=adapter,
        user_text="Test",
        draft_body="Fallback runtime.",
        detected_intent="ordinary_conversation",
        route="ordinary_dialogue",
        cognitive_frame={},
        response_policy={},
        executor_preflight=resolve_model_executor(adapter),
    )

    assert result.used is False
    assert result.reason == "selected_runtime_fallback_candidate"
    assert result.endpoint_used == "/api/chat"
    assert result.adapter_response == diagnostic
    assert result.candidate_validation == evaluation.to_dict()
