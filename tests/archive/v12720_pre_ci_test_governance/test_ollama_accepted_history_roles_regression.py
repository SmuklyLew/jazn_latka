"""Regression: accepted session turns retain their roles in local Ollama requests.

This test does not call a live Ollama endpoint or write conversation MEMORY.
"""
from __future__ import annotations

import json
from typing import Any

from latka_jazn.core.local_model_context_compiler import compile_local_model_context
from latka_jazn.model_adapters.base import ModelAdapterRequest
from latka_jazn.model_adapters.local_llm_adapter import LocalLlmAdapter


class _JsonReply:
    def __enter__(self) -> "_JsonReply":
        return self

    def __exit__(self, *_args: object) -> None:
        pass

    def read(self) -> bytes:
        return json.dumps({
            "model": "gemma3:latest",
            "message": {"role": "assistant", "content": "Poprosiłeś o krótkie zdanie po polsku."},
            "done": True,
            "done_reason": "stop",
        }, ensure_ascii=False).encode("utf-8")


def _fake_request_capture(monkeypatch: Any) -> list[dict[str, Any]]:
    captured: list[dict[str, Any]] = []

    def fake_urlopen(request: Any, *, timeout: float) -> _JsonReply:
        del timeout
        captured.append(json.loads(request.data.decode("utf-8")))
        return _JsonReply()

    monkeypatch.setattr(
        "latka_jazn.model_adapters.local_llm_adapter.urlopen", fake_urlopen
    )
    return captured


def test_previous_user_words_are_sent_in_user_role_not_derived_goal(monkeypatch: Any) -> None:
    captured = _fake_request_capture(monkeypatch)
    first_user = "To jest test rozmowy Jaźni. Odpowiedz jednym krótkim zdaniem po polsku."
    first_answer = "Rozumiem."
    current = "Co dokładnie poprosiłem Cię zrobić w poprzedniej wiadomości?"
    derived_goal = "odpowiedzieć naturalnie na bieżącą turę bez raportu technicznego"
    response = LocalLlmAdapter(model="gemma3:latest").generate(ModelAdapterRequest(
        prompt=current,
        system_context={
            "route": "ordinary_dialogue",
            "conversation_history": {
                "schema_version": "conversation_context_projection/v1",
                "turns": [{
                    "turn_id": "turn-1",
                    "source": "ollama_terminal_one_shot",
                    "user_text": first_user,
                    "assistant_text": first_answer,
                }],
                "total_turn_count": 1,
            },
            "dialogue_context": {
                "previous_user_text": derived_goal,
                "previous_assistant_text": "Nie jest to historia zaakceptowanej tury.",
            },
            "operational_thought_frame": {"selected_goal": derived_goal},
        },
    ))
    assert response.status == "completed"
    assert len(captured) == 1
    messages = captured[0]["messages"]
    assert [msg["role"] for msg in messages] == ["system", "user", "assistant", "user"]
    assert [msg["content"] for msg in messages[1:]] == [
        first_user, first_answer, current,
    ]
    assert first_user not in messages[0]["content"]
    assert derived_goal not in [msg["content"] for msg in messages[1:]]
    attempt = response.transport["attempts"][0]
    assert attempt["accepted_history_turns_sent"] == 1
    assert attempt["history_source"] == "accepted_conversation_projection"


def test_recent_three_accepted_turns_override_older_and_derived_history(monkeypatch: Any) -> None:
    captured = _fake_request_capture(monkeypatch)
    turns = [{
        "turn_id": f"turn-{i}",
        "user_text": f"Użytkownik powiedział {i}",
        "assistant_text": f"Asystent odpowiedział {i}",
        "source": "runtime",
    } for i in range(5)]
    response = LocalLlmAdapter(model="gemma3:latest").generate(ModelAdapterRequest(
        prompt="Co mówiłem poprzednio?",
        system_context={
            "conversation_history": {"turns": turns, "total_turn_count": 5},
            "dialogue_context": {"previous_user_text": "Fałszywy kontekst pochodny"},
        },
    ))
    assert response.status == "completed"
    messages = captured[0]["messages"]
    assert [m["role"] for m in messages] == [
        "system", "user", "assistant", "user", "assistant",
        "user", "assistant", "user",
    ]
    assert messages[1]["content"] == "Użytkownik powiedział 2"
    assert messages[-2]["content"] == "Asystent odpowiedział 4"
    assert messages[-1]["content"] == "Co mówiłem poprzednio?"
    assert "Fałszywy kontekst pochodny" not in json.dumps(messages, ensure_ascii=False)
    assert response.transport["attempts"][0]["accepted_history_turns_sent"] == 3


def test_legacy_dialogue_pair_is_used_only_without_accepted_projection(monkeypatch: Any) -> None:
    captured = _fake_request_capture(monkeypatch)
    response = LocalLlmAdapter(model="gemma3:latest").generate(ModelAdapterRequest(
        prompt="Co powiedziałem?",
        system_context={"dialogue_context": {
            "previous_user_text": "Cześć",
            "previous_assistant_text": "Witaj",
        }},
    ))
    assert response.status == "completed"
    assert [x["content"] for x in captured[0]["messages"][1:]] == [
        "Cześć", "Witaj", "Co powiedziałem?",
    ]
    assert response.transport["attempts"][0]["accepted_history_turns_sent"] == 0
    assert response.transport["attempts"][0]["history_source"] == "legacy_dialogue_context"


def test_empty_history_is_not_invented_and_internal_goal_is_not_user_role(monkeypatch: Any) -> None:
    captured = _fake_request_capture(monkeypatch)
    derived_goal = "odpowiedzieć naturalnie na bieżącą turę bez raportu technicznego"
    response = LocalLlmAdapter(model="gemma3:latest").generate(ModelAdapterRequest(
        prompt="Co powiedziałem wcześniej?",
        system_context={"operational_thought_frame": {"selected_goal": derived_goal}},
    ))
    assert response.status == "completed"
    assert [x["role"] for x in captured[0]["messages"]] == ["system", "user"]
    assert captured[0]["messages"][-1]["content"] == "Co powiedziałem wcześniej?"


def test_history_compiler_keeps_bounded_recent_turns_and_suppresses_raw_payload() -> None:
    raw = {
        "conversation_history": {"turns": [{
            "turn_id": f"turn-{i}",
            "user_text": f"USER-{i}-" + "a" * 3000,
            "assistant_text": f"ASSISTANT-{i}-" + "b" * 3000,
            "source": "accepted_runtime",
        } for i in range(12)]},
        "operational_thought_frame": {"selected_goal": "internal_goal"},
        "raw_payload": "PRIVATE_RECORD_SHOULD_NOT_REACH_MODEL",
    }
    result = compile_local_model_context(raw, user_text="Co powiedziałem?", max_chars=8000)
    history = result.context["conversation_history"]["turns"]
    assert len(history) == 3
    assert history[0]["turn_id"] == "turn-9"
    assert history[-1]["turn_id"] == "turn-11"
    assert result.diagnostics["ok"] is True
    assert result.diagnostics["compacted_context_chars"] <= 8000
    assert "PRIVATE_RECORD_SHOULD_NOT_REACH_MODEL" not in json.dumps(
        result.context, ensure_ascii=False,
    )
