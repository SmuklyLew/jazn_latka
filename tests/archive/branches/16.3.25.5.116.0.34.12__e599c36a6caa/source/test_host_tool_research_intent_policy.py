from __future__ import annotations

import pytest

from latka_jazn.core.host_tool_capabilities import build_host_tool_capability_snapshot
from latka_jazn.core.host_tool_turn_policy import (
    build_host_tool_turn_policy,
    validate_tool_evidence_against_policy,
)


@pytest.mark.parametrize("message", [
    "Poszukaj jak to programować w wiarygodnych źródłach.",
    "Przeszukaj internet, zweryfikuj dokumentację.",
    "Sprawdź w internecie dostępne narzędzia ChatGPT.",
    "Wyszukaj źródła techniczne dla MCP.",
])
def test_imperative_research_requires_real_web_evidence(message: str) -> None:
    available = build_host_tool_capability_snapshot(
        {"tools": [{"name": "web.run", "available": True}]}, env={}
    )
    policy = build_host_tool_turn_policy(
        user_text=message, detected_intent="ordinary_conversation",
        route="ordinary_dialogue", nlg_plan={"source_policy": "runtime_only"},
        host_tool_capabilities=available,
    )
    assert "web.run" in policy["requested_tools"]
    assert "web.run" in policy["required_tools"]
    assert "required_tool_evidence_missing:web.run" in validate_tool_evidence_against_policy([], policy)


def test_explicit_research_without_host_web_reports_unavailable() -> None:
    unavailable = build_host_tool_capability_snapshot(
        {"tools": [{"name": "web.run", "available": False}]}, env={}
    )
    policy = build_host_tool_turn_policy(
        user_text="Poszukaj informacji o MCP", detected_intent="ordinary_conversation",
        route="ordinary_dialogue", host_tool_capabilities=unavailable,
    )
    assert policy["required_tools_unavailable"] == ["web.run"]
    assert "required_host_tool_unavailable:web.run" in validate_tool_evidence_against_policy([], policy)


def test_unrelated_conversation_does_not_require_web() -> None:
    policy = build_host_tool_turn_policy(
        user_text="Dzień dobry, porozmawiajmy o planach.",
        detected_intent="ordinary_conversation", route="ordinary_dialogue",
    )
    assert "web.run" not in policy["requested_tools"]
