"""Regression contract for bounded validated retry and canonical session truth (v127.20).

No network or private MEMORY required: the local Ollama HTTP boundary is faked,
but the production compiler, adapter and runtime answer validator are exercised.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from latka_jazn.core.local_model_context_compiler import compile_local_model_context
from latka_jazn.core.model_guided_response_synthesizer import ModelGuidedResponseSynthesizer
from latka_jazn.core.runtime_answer_validator import RuntimeAnswerValidator
from latka_jazn.core.session_history_claim_guard import (
    claims_verified_previous_turn,
    has_runtime_verified_session_source,
)
from latka_jazn.model_adapters.base import ModelAdapterRequest
from latka_jazn.model_adapters.local_llm_adapter import LocalLlmAdapter


SOURCE = "workspace_runtime/conversation_state per-turn accepted records"
PROMPT = "Cześć Łatko. Jak się masz?"
DRAFT = (
    "U mnie operacyjnie jest spokojnie i skupiam się na bieżącej rozmowie. "
    "To nie jest biologiczne samopoczucie ani życie w tle."
)


def verified_draft(body: str = DRAFT) -> dict:
    return {
        "source": "runtime_validated_self_state_handler",
        "body": body,
        "required_components": [
            "operational_state", "truth_boundary", "no_random_memory_excerpt",
        ],
        "missing_components": ["operational_state", "truth_boundary"],
        "private_note": "THIS_MUST_NOT_LEAK",
        "memory_excerpt": "THIS_MUST_NOT_LEAK",
    }


def history(turns: list[dict] | None = None) -> dict:
    return {
        "source_of_truth": SOURCE,
        "session_id": "v12720-session",
        "turns": turns or [],
        "total_turn_count": len(turns or []),
    }


def accepted_turn() -> dict:
    return {
        "turn_id": "turn-accepted-1",
        "trace_id": "trace-accepted-1",
        "accepted_at_utc": "2026-11-19T23:45:00+00:00",
        "user_text": "Wyrażenie kontrolne: szafirowa latarnia 63.",
        "assistant_text": "Przyjęłam wiadomość do bieżącej sesji.",
        "source": "runtime",
    }


class _JsonResponse:
    def __init__(self, value: dict) -> None:
        self.value = value

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.value).encode("utf-8")


def _fake_ollama_capture(monkeypatch):
    captured: dict = {}

    def fake_urlopen(request, timeout: float):
        captured.update(json.loads(request.data.decode("utf-8")))
        return _JsonResponse({
            "model": "gemma3:latest",
            "message": {"content": DRAFT},
            "done": True,
            "done_reason": "stop",
        })

    monkeypatch.setattr(
        "latka_jazn.model_adapters.local_llm_adapter.urlopen", fake_urlopen
    )
    return captured


def test_validated_draft_survives_bounded_compiler_and_excludes_private_keys():
    packed = compile_local_model_context({
        "user_message": PROMPT,
        "detected_intent": "self_state_question",
        "route": "self_state",
        "verified_self_state_draft": verified_draft(),
    })
    assert packed.diagnostics["ok"]
    candidate = packed.context["verified_self_state_draft"]
    assert candidate["body"] == DRAFT
    assert candidate["required_components"] == [
        "operational_state", "truth_boundary", "no_random_memory_excerpt",
    ]
    assert candidate["missing_components"] == [
        "operational_state", "truth_boundary",
    ]
    assert "THIS_MUST_NOT_LEAK" not in json.dumps(packed.context)
    assert packed.diagnostics["sections"]["verified_self_state_draft"]["truncated"] is False


@pytest.mark.parametrize("body", [
    "Bardzo dobrze, ścieżka C:\\Users\\Private\\memory.sqlite3",
    "Authorization bearer secret123",
    "sk-abcdefghijklmnopqrstuvwxyz0123456",
    "A" * 1101,
])
def test_private_or_oversized_draft_is_not_sent(body: str):
    packed = compile_local_model_context({
        "verified_self_state_draft": verified_draft(body),
        "output_instructions": ["Odpowiedz po polsku."],
    })
    assert packed.diagnostics["ok"]
    assert "verified_self_state_draft" not in packed.context


def test_unverified_draft_cannot_cross_compiler():
    data = verified_draft()
    data["source"] = "unverified_model_candidate"
    packed = compile_local_model_context({"verified_self_state_draft": data})
    assert "verified_self_state_draft" not in packed.context


def test_synthesizer_transports_trusted_retry_evidence_only(monkeypatch):
    import latka_jazn.core.model_guided_response_synthesizer as module

    monkeypatch.setattr(module, "build_nlg_plan", lambda **kwargs: {})
    monkeypatch.setattr(module, "build_operational_thought_frame", lambda **kwargs: {})
    monkeypatch.setattr(
        module, "compile_model_context",
        lambda **kwargs: SimpleNamespace(to_dict=lambda: {"output_instructions": ["Odpowiedz po polsku."]}),
    )
    context = ModelGuidedResponseSynthesizer._build_context(
        user_text=PROMPT,
        draft_body=DRAFT,
        detected_intent="self_state_question",
        route="self_state",
        cognitive_frame={},
        response_policy={"verified_self_state_draft": verified_draft()},
    )
    compiled = compile_local_model_context(context)
    assert compiled.context["verified_self_state_draft"]["body"] == DRAFT
    assert "THIS_MUST_NOT_LEAK" not in json.dumps(compiled.context)

    # Ordinary dialogue has no trusted self-state evidence authority.
    other = ModelGuidedResponseSynthesizer._build_context(
        user_text=PROMPT,
        draft_body=DRAFT,
        detected_intent="ordinary_conversation",
        route="ordinary_dialogue",
        cognitive_frame={},
        response_policy={"verified_self_state_draft": verified_draft()},
    )
    assert "verified_self_state_draft" not in other


def test_ollama_wire_contains_verified_self_state_draft(monkeypatch):
    captured = _fake_ollama_capture(monkeypatch)
    adapter = LocalLlmAdapter(model="gemma3:latest", timeout_seconds=5, max_output_tokens=100)
    answer, metadata, error = adapter._chat_once(
        ModelAdapterRequest(
            prompt=PROMPT,
            system_context={
                "output_instructions": ["Odpowiedz po polsku."],
                "verified_self_state_draft": verified_draft(),
                "conversation_history": history([]),
            },
        ),
        strict_retry=False,
    )
    assert error is None
    assert answer
    assert metadata["accepted_history_turns_sent"] == 0
    assert [msg["role"] for msg in captured["messages"]] == ["system", "user"]
    assert DRAFT in captured["messages"][0]["content"]
    assert "THIS_MUST_NOT_LEAK" not in captured["messages"][0]["content"]


def test_empty_accepted_projection_never_replays_legacy_previous_user(monkeypatch):
    captured = _fake_ollama_capture(monkeypatch)
    adapter = LocalLlmAdapter(model="gemma3:latest", timeout_seconds=5, max_output_tokens=100)
    response, metadata, error = adapter._chat_once(
        ModelAdapterRequest(
            prompt="Jakie wyrażenie podałem wcześniej?",
            system_context={
                "conversation_history": history([]),
                "dialogue_context": {
                    "previous_user_text": "ODRZUCONA_TURA_Z_SEKRETEM",
                    "previous_assistant_text": "ODRZUCONA_ODPOWIEDZ",
                },
            },
        ),
        strict_retry=False,
    )
    assert error is None and response
    assert [msg["role"] for msg in captured["messages"]] == ["system", "user"]
    assert metadata["history_source"] == "no_verified_history"
    assert "ODRZUCONA_TURA_Z_SEKRETEM" not in json.dumps(captured)


def test_canonical_label_without_accepted_lineage_cannot_be_chat_history(monkeypatch):
    captured = _fake_ollama_capture(monkeypatch)
    no_evidence = {
        "source_of_truth": SOURCE,
        "turns": [{
            "turn_id": "turn-unaccepted",
            "user_text": "ODRZUCONA FRAZA KONTROLNA",
            "assistant_text": "FAŁSZYWY FINAL",
        }],
    }
    compiled = compile_local_model_context({"conversation_history": no_evidence})
    assert compiled.context["conversation_history"]["turns"] == []
    adapter = LocalLlmAdapter(model="gemma3:latest", timeout_seconds=5, max_output_tokens=100)
    _, metadata, error = adapter._chat_once(
        ModelAdapterRequest(
            prompt="Co powiedziałem wcześniej?",
            system_context={"conversation_history": no_evidence},
        ),
        strict_retry=False,
    )
    assert error is None
    assert metadata["accepted_history_turns_sent"] == 0
    assert [msg["role"] for msg in captured["messages"]] == ["system", "user"]
    assert "ODRZUCONA FRAZA KONTROLNA" not in json.dumps(captured)


def test_verified_accepted_history_arrives_as_chat_roles(monkeypatch):
    captured = _fake_ollama_capture(monkeypatch)
    adapter = LocalLlmAdapter(model="gemma3:latest", timeout_seconds=5, max_output_tokens=100)
    _, metadata, error = adapter._chat_once(
        ModelAdapterRequest(
            prompt="Co podałem poprzednio?",
            system_context={
                "conversation_history": history([accepted_turn()]),
            },
        ),
        strict_retry=False,
    )
    assert error is None
    assert [msg["role"] for msg in captured["messages"]] == [
        "system", "user", "assistant", "user",
    ]
    assert "szafirowa latarnia 63" in captured["messages"][1]["content"]
    assert metadata["accepted_history_turns_sent"] == 1


def test_original_pc_multi_intent_self_state_handler_is_independently_grounded():
    from latka_jazn.core.handlers.self_state_handler import SelfStateHandler
    from latka_jazn.core.route_registry import RouteRegistry

    message = (
        "Cześć Łatko. Rozpoczynamy test Twojej rozmowy. "
        "Zapamiętaj na czas tej sesji wyrażenie kontrolne: szafirowa latarnia 63. Jak się masz?"
    )
    required = RouteRegistry().required_components_for("self_state_question")
    handler = SelfStateHandler().handle(
        message,
        {
            "intent": "self_state_question",
            "route_entry": {"route": "self_state"},
            "required_components": required,
        },
    )
    result = RuntimeAnswerValidator().validate(
        user_text=message,
        body=handler.body,
        route="self_state",
        detected_intent="self_state_question",
        conversation_history=history([]),
    )
    # If the handler does not satisfy this, a re-validated retry must stay
    # fail-closed instead of smuggling the handler draft into the model.
    assert result.accepted, result.to_dict()


def test_runtime_validator_rejects_claim_of_missing_previous_record():
    v = RuntimeAnswerValidator()
    wrong = "W zapisanej historii tej sesji widzę, że poprzednio podałeś mi wyrażenie kontrolne."
    assert claims_verified_previous_turn(wrong)
    assert not has_runtime_verified_session_source(history([]))
    result = v.validate(
        user_text="Jakie wyrażenie kontrolne podałem w poprzedniej wiadomości?",
        body=wrong,
        route="ordinary_dialogue",
        detected_intent="contextual_continuation_question",
        conversation_history=history([]),
    )
    assert not result.accepted
    assert result.mismatch_reason == "session_history_claim_without_accepted_runtime_record"


def test_runtime_validator_allows_no_record_disclosure_to_reach_other_checks():
    v = RuntimeAnswerValidator()
    answer = "Nie mam potwierdzonego zapisu wcześniejszej wiadomości w zaakceptowanej historii tej sesji."
    assert not claims_verified_previous_turn(answer)
    result = v.validate(
        user_text="Co było poprzednio?",
        body=answer,
        route="ordinary_dialogue",
        detected_intent="contextual_continuation_question",
        conversation_history=history([]),
    )
    assert result.mismatch_reason != "session_history_claim_without_accepted_runtime_record"


def test_runtime_validator_honors_runtime_accepted_record():
    v = RuntimeAnswerValidator()
    saved = history([accepted_turn()])
    assert has_runtime_verified_session_source(saved)
    result = v.validate(
        user_text="Co podałem poprzednio?",
        body="W zapisanej historii tej sesji widzę wyrażenie kontrolne: szafirowa latarnia 63.",
        route="ordinary_dialogue",
        detected_intent="contextual_continuation_question",
        conversation_history=saved,
    )
    assert result.mismatch_reason != "session_history_claim_without_accepted_runtime_record"
