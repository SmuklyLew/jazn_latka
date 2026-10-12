from __future__ import annotations

from latka_jazn.core.route_registry import RouteRegistry


def test_characterization_major_route_families() -> None:
    registry = RouteRegistry()
    expected = {
        "ordinary_conversation": ("ordinary_dialogue", "OrdinaryDialogueHandler"),
        "runtime_health_check": ("runtime_health_check", "CapabilityStatusHandler"),
        "memory_experience_question": (
            "memory_experience_recall",
            "MemoryExperienceRecallHandler",
        ),
        "external_research_request": ("external_research", "ExternalResearchHandler"),
        "self_state_question": ("self_state", "SelfStateHandler"),
    }

    for intent, (route, handler) in expected.items():
        entry = registry.resolve(intent)
        assert entry.intent == intent
        assert entry.route == route
        assert entry.handler_name == handler


def test_characterization_unknown_intent_remains_explicit_fallback() -> None:
    entry = RouteRegistry().resolve("v108_unknown_intent")
    assert entry.route == "fallback"
    assert entry.handler_name == "FallbackHandler"
