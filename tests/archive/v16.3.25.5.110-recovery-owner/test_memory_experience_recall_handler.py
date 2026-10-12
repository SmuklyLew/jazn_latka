from __future__ import annotations

import ast
import inspect
import textwrap

from latka_jazn.core.engine import JaznEngine
from latka_jazn.core.handlers.memory_experience_recall_handler import (
    MemoryExperienceRecallHandler,
)
from latka_jazn.core.handlers.ordinary_dialogue_handler import OrdinaryDialogueHandler
from latka_jazn.core.route_handler_dispatcher import RouteHandlerDispatcher
from latka_jazn.core.route_registry import RouteRegistry
from latka_jazn.core.runtime_response_synthesizer import RuntimeResponseSynthesizer


def _memory_context() -> dict:
    return {
        "memory_recall_payload": {
            "schema_version": "memory_recall_content/test",
            "items": [
                {
                    "item_id": "memory-2025-1",
                    "content_excerpt": "W czerwcu rozmawialiśmy o wspólnym spacerze.",
                    "source": "conversation_archive / conversation-2025",
                    "timestamp": "2025-06-12T10:00:00+00:00",
                    "grounding": "conversation_archive_v1+fts_v1",
                    "confidence": 0.96,
                }
            ],
        },
        "episodes": [
            {
                "scene": "NIEUZIEMIONY DECOY SPOZA ZAMROŻONEGO PAYLOADU",
                "source": "legacy_fallback",
            }
        ],
    }


def test_memory_experience_intents_use_dedicated_handler() -> None:
    registry = RouteRegistry()
    for intent in (
        "memory_experience_question",
        "substantive_question_about_last_year",
    ):
        entry = registry.resolve(intent)
        assert entry.route == "memory_experience_recall"
        assert entry.handler_name == "MemoryExperienceRecallHandler"
        assert set(entry.required_components) == {
            "memory_content",
            "source_or_index_status",
            "truth_boundary",
            "no_current_turn_echo",
        }
    assert "memory_experience_question" not in OrdinaryDialogueHandler.handled_intents
    assert (
        "substantive_question_about_last_year"
        not in OrdinaryDialogueHandler.handled_intents
    )


def test_dispatcher_renders_only_frozen_memory_recall_payload() -> None:
    entry = RouteRegistry().resolve("memory_experience_question")
    result = RouteHandlerDispatcher().dispatch(
        entry,
        "Co wtedy wspominasz?",
        {"memory_context": _memory_context()},
    )

    assert result.handler_name == "MemoryExperienceRecallHandler"
    assert result.route == "memory_experience_recall"
    assert "W czerwcu rozmawialiśmy o wspólnym spacerze." in result.body
    assert "conversation_archive / conversation-2025" in result.body
    assert "NIEUZIEMIONY DECOY" not in result.body
    assert result.data["memory_recall_payload_frozen"] is True
    assert [item["item_id"] for item in result.memory_sources] == [
        "memory-2025-1"
    ]


def test_empty_or_ungrounded_payload_fails_closed() -> None:
    result = MemoryExperienceRecallHandler().handle(
        "Powspominaj ten dzień.",
        {
            "intent": "memory_experience_question",
            "memory_context": {
                "memory_recall_payload": {
                    "items": [
                        {
                            "content_excerpt": "Fragment bez źródła.",
                        }
                    ]
                },
                "conversation_archive_hits": [
                    {
                        "excerpt": "DECOY Z SUROWEGO KONTEKSTU",
                        "source": "archive",
                    }
                ],
            },
        },
    )

    assert result.data["status"] == "grounded_payload_empty"
    assert result.memory_sources == []
    assert "nie mogę uczciwie wygenerować wspomnienia" in result.body
    assert "Fragment bez źródła" not in result.body
    assert "DECOY Z SUROWEGO KONTEKSTU" not in result.body


def test_current_turn_echo_is_not_accepted_as_memory() -> None:
    user_text = "To jest bieżąca wiadomość, a nie historyczne wspomnienie."
    result = MemoryExperienceRecallHandler().handle(
        user_text,
        {
            "memory_context": {
                "memory_recall_payload": {
                    "items": [
                        {
                            "content_excerpt": user_text,
                            "source": "current_turn",
                        }
                    ]
                }
            }
        },
    )

    assert result.data["status"] == "grounded_payload_empty"
    assert result.memory_sources == []


def test_bounded_handler_does_not_claim_three_items_are_the_entire_payload() -> None:
    result = MemoryExperienceRecallHandler().handle(
        "Powspominaj 2025 rok.",
        {
            "memory_context": {
                "memory_recall_payload": {
                    "items": [
                        {
                            "item_id": f"memory-{index}",
                            "content_excerpt": f"Źródłowy fragment numer {index}.",
                            "source": f"archive/{index}",
                        }
                        for index in range(1, 5)
                    ]
                }
            }
        },
    )

    assert result.data["filtered_item_count"] == 3
    assert "Źródłowy fragment numer 3." in result.body
    assert "Źródłowy fragment numer 4." not in result.body
    assert "wybrane, źródłowo uziemione fragmenty" in result.body
    assert "cała treść" not in result.body


def test_runtime_repair_uses_the_same_frozen_payload() -> None:
    result = RuntimeResponseSynthesizer().synthesize(
        user_text="Co wtedy wspominasz?",
        detected_intent="memory_experience_question",
        original_body="Nietrafiony tekst.",
        route="memory_experience_recall",
        validation={"must_regenerate": True},
        memory_context=_memory_context(),
    )

    assert result.should_override is True
    assert result.handler_name == "MemoryExperienceRecallHandler"
    assert result.route == "memory_experience_recall"
    assert "W czerwcu rozmawialiśmy o wspólnym spacerze." in result.body
    assert "NIEUZIEMIONY DECOY" not in result.body


def test_both_local_engine_repair_calls_forward_memory_context() -> None:
    source = textwrap.dedent(inspect.getsource(JaznEngine.process_turn))
    tree = ast.parse(source)
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "synthesize"
        and isinstance(node.func.value, ast.Attribute)
        and node.func.value.attr == "runtime_response_synthesizer"
    ]

    assert len(calls) == 2
    assert all(
        "memory_context" in {keyword.arg for keyword in call.keywords}
        for call in calls
    )
