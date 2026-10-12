from __future__ import annotations

from pathlib import Path
from typing import Any
import json

import pytest

from latka_jazn.config import JaznConfig
from latka_jazn.core.local_model_context_compiler import compile_local_model_context
from latka_jazn.core.self_knowledge_contract import build_self_knowledge_packet
from latka_jazn.core.startup_contract import update_history_status
from latka_jazn.memory.dream_sandbox import DreamSandbox
from latka_jazn.memory.memory_sync_runtime import MemorySyncRuntime
from latka_jazn.memory.memory_tier_store import MemoryTierStore
from latka_jazn.model_adapters.base import ModelAdapterRequest
from latka_jazn.model_adapters.local_llm_adapter import LocalLlmAdapter


class _JsonResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload, ensure_ascii=False).encode("utf-8")


def _large_context(user_text: str) -> dict[str, Any]:
    relevant = {
        "item_id": "evidence-performance-1",
        "excerpt": "Kontekst Ollama musi zachować wymagane dowody i limit transportu.",
        "source": "verified-test",
        "confidence": 0.99,
        "relevance_reason": "Ollama context performance",
    }
    irrelevant = [
        {
            "item_id": f"evidence-other-{index}",
            "excerpt": "mniej istotny wpis " + ("x" * 1200),
            "source": "verified-test",
            "confidence": 0.4,
        }
        for index in range(40)
    ]
    return {
        "schema_version": "historical-large-context/v1",
        "user_message": user_text,
        "route": "ordinary_dialogue",
        "detected_intent": "technical_question",
        "nlg_plan": {"response_mode": "direct", "detail": "x" * 200_000},
        "dialogue_context": {
            "previous_user_text": "Poprzednia wiadomość",
            "previous_assistant_text": "Poprzednia odpowiedź",
            "dialogue_task_state": {"task_key": "goal-context-1"},
        },
        "allowed_memory_items": [relevant, dict(relevant), *irrelevant],
        "required_reference_ids": {
            "goal": ["goal-context-1"],
            "constraint": ["constraint-budget-1"],
            "evidence": ["evidence-performance-1"],
        },
        "raw_payload": "PRIVATE_RAW_MARKER:" + ("r" * 5_900_000),
        "private_chain_of_thought": "PRIVATE_REASONING_MARKER",
    }


def test_historical_large_ollama_context_is_bounded_grounded_and_content_free(
    monkeypatch,
) -> None:
    user_text = "Jak działa kompilator kontekstu Ollama?"
    context = _large_context(user_text)
    captured: dict[str, Any] = {}

    def fake_urlopen(request, timeout: float):
        del timeout
        captured.update(json.loads(request.data.decode("utf-8")))
        return _JsonResponse({
            "model": "local-test:latest",
            "message": {"content": "Kontekst pozostaje ograniczony i ugruntowany."},
            "done": True,
            "done_reason": "stop",
            "prompt_eval_count": 8195,
        })

    monkeypatch.setattr(
        "latka_jazn.model_adapters.local_llm_adapter.urlopen",
        fake_urlopen,
    )
    adapter = LocalLlmAdapter(
        model="local-test:latest",
        timeout_seconds=5,
        max_output_tokens=128,
    )
    response = adapter.generate(
        ModelAdapterRequest(prompt=user_text, system_context=context)
    )

    assert response.status == "completed"
    attempt = response.transport["attempts"][0]
    assert attempt["original_context_chars"] > 5_900_000
    assert attempt["compacted_context_chars"] <= 16_000
    assert attempt["request_bytes"] <= attempt["request_max_bytes"]
    assert attempt["required_reference_ids_preserved"] is True
    assert attempt["deduplicated_current_user_message"] is True
    assert attempt["prompt_eval_count"] == 8195
    assert attempt["raw_payload_included"] is False
    assert attempt["private_reasoning_included"] is False

    wire_text = json.dumps(captured, ensure_ascii=False)
    assert "PRIVATE_RAW_MARKER" not in wire_text
    assert "PRIVATE_REASONING_MARKER" not in wire_text
    assert wire_text.count(user_text) == 1
    assert "goal-context-1" in wire_text
    assert "constraint-budget-1" in wire_text
    assert "evidence-performance-1" in wire_text
    allowed = json.loads(captured["messages"][0]["content"].split("KONTEKST_JAZNI_JSON:\n", 1)[1])[
        "allowed_memory_items"
    ]
    assert sum(item["item_id"] == "evidence-performance-1" for item in allowed) == 1


def test_required_reference_overflow_fails_closed_before_http(monkeypatch) -> None:
    called = False

    def forbidden_urlopen(*_args, **_kwargs):
        nonlocal called
        called = True
        raise AssertionError("HTTP must not run after context rejection")

    monkeypatch.setattr(
        "latka_jazn.model_adapters.local_llm_adapter.urlopen",
        forbidden_urlopen,
    )
    response = LocalLlmAdapter(model="local-test:latest").generate(
        ModelAdapterRequest(
            prompt="Krótka wiadomość",
            system_context={
                "required_reference_ids": {
                    "goal": [f"goal-{index}" for index in range(65)]
                }
            },
        )
    )

    assert called is False
    assert response.status == "context_rejected"
    assert response.transport["attempts"][0]["error_code"] == (
        "local_context_required_reference_overflow"
    )
    assert response.status_snapshot is not None
    assert response.status_snapshot.endpoint_reachable is None


def test_direct_user_prompt_budget_fails_closed_before_http(monkeypatch) -> None:
    monkeypatch.setattr(
        "latka_jazn.model_adapters.local_llm_adapter.urlopen",
        lambda *_args, **_kwargs: pytest.fail("HTTP must not run for oversized prompt"),
    )
    response = LocalLlmAdapter(model="local-test:latest").generate(
        ModelAdapterRequest(prompt="u" * 8_001, system_context={"route": "dialogue"})
    )
    assert response.status == "context_rejected"
    assert response.transport["attempts"][0]["error_code"] == (
        "local_model_user_prompt_budget_exceeded"
    )


def test_local_request_rolling_p50_p95_is_numeric_and_content_free(monkeypatch) -> None:
    prompt_counts = iter((100, 200, 1000))

    def fake_urlopen(*_args, **_kwargs):
        return _JsonResponse({
            "model": "local-test:latest",
            "message": {"content": "To jest poprawna polska odpowiedź."},
            "done": True,
            "prompt_eval_count": next(prompt_counts),
        })

    monkeypatch.setattr(
        "latka_jazn.model_adapters.local_llm_adapter.urlopen",
        fake_urlopen,
    )
    adapter = LocalLlmAdapter(model="local-test:latest")
    for index in range(3):
        response = adapter.generate(
            ModelAdapterRequest(
                prompt=f"Wiadomość numer {index}",
                system_context={"route": "ordinary_dialogue"},
            )
        )
        assert response.status == "completed"

    summary = adapter.describe()["local_request_performance"]
    assert summary["sample_count"] == 3
    assert summary["prompt_tokens_p50"] == 200.0
    assert summary["prompt_tokens_p95"] == 1000.0
    assert summary["request_bytes_p50"] is not None
    assert summary["request_bytes_p95"] is not None
    assert summary["latency_ms_p50"] is not None
    assert summary["latency_ms_p95"] is not None
    assert summary["raw_payload_recorded"] is False
    assert summary["content_recorded"] is False


def test_context_maximum_is_hard_capped_even_if_operator_value_is_larger() -> None:
    result = compile_local_model_context(
        {"nlg_plan": {"detail": "x" * 100_000}},
        max_chars=999_999,
    )
    assert result.diagnostics["context_max_chars"] == 32_768
    assert result.diagnostics["compacted_context_chars"] <= 32_768


@pytest.mark.parametrize(
    ("provider", "endpoint", "reason"),
    [
        ("openai", "https://api.openai.com/v1", "background_rest_requires_local_provider"),
        ("openai_compatible", "https://example.invalid/v1", "background_rest_endpoint_not_loopback"),
    ],
)
def test_autonomous_dream_rejects_paid_or_remote_provider(
    tmp_path,
    monkeypatch,
    provider: str,
    endpoint: str,
    reason: str,
) -> None:
    class _Adapter:
        def describe(self) -> dict[str, Any]:
            return {
                "provider": provider,
                "endpoint": endpoint,
                "model": "configured-model",
                "configured": True,
                "can_attempt_model_guided_speech": True,
            }

        def generate(self, _request):
            pytest.fail("rejected autonomous provider must not generate")

    monkeypatch.setattr(
        "latka_jazn.memory.dream_sandbox.build_model_adapter",
        lambda _config: _Adapter(),
    )
    readiness = DreamSandbox(JaznConfig(root=tmp_path)).readiness()
    assert readiness["rest_dream_ready"] is False
    assert readiness["reason"] == reason


def test_cloud_status_is_opt_in_local_first_and_does_not_probe(tmp_path) -> None:
    cfg = JaznConfig(root=tmp_path)
    with MemoryTierStore(cfg.memory_tier_db_path):
        pass
    status = MemorySyncRuntime(cfg).status(probe_remote=False)
    assert status["configuration"]["mode"] == "off"
    assert status["configuration"]["enabled"] is False
    assert status["configuration"]["secret_material_exposed"] is False
    assert status["remote_probe_performed"] is False
    assert status["cloud_sync_ready"] is False
    assert status["local_memory_ready_independent_of_cloud"] is True
    assert status["local_replication_state"]["store_exists"] is True


def test_missing_optional_history_indices_are_not_false_warnings(tmp_path) -> None:
    status = update_history_status(tmp_path)
    assert status["status"] == "optional_not_configured"
    assert status["required"] is False
    assert status["warning"] is False
    assert status["missing_is_error"] is False

    repository_root = Path(__file__).resolve().parents[1]
    packet = build_self_knowledge_packet(JaznConfig(root=repository_root))
    optional_roles = {"procedural_update_history", "archived_manifest_history"}
    assert not optional_roles.intersection(
        item["role"] for item in packet.source_statuses
    )
    learned = packet.learned_procedures_status
    assert learned["docs_update_history_status"] == "optional_not_configured"
    assert learned["archived_manifest_history_status"] == "optional_not_configured"
    assert learned["optional_history_required"] is False
    assert learned["optional_history_warning"] is False
