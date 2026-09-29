from __future__ import annotations

from pathlib import Path

from latka_jazn.config import JaznConfig
from latka_jazn.core.handlers.self_architecture_audit_handler import SelfArchitectureAuditHandler
from latka_jazn.core.host_tool_capabilities import build_host_tool_capability_snapshot
from latka_jazn.core.host_tool_turn_policy import (
    build_host_tool_turn_policy,
    validate_tool_evidence_against_policy,
)
from latka_jazn.core.route_registry import RouteRegistry
from latka_jazn.nlp.dialogue_intent_classifier import DialogueIntentClassifier
from latka_jazn.version import PACKAGE_VERSION_FULL


UPDATE_CONTINUATION = (
    "Sprawdź też kod źródłowy, czy jest poprawnie i bez błędnia wprowadzony w system Jaźni. "
    "Pracuj dobrze i z dostępem do internetu aż aktualizacja będzie pełnym, zdrowym "
    "release candidate i gotowym do scalenia."
)


def test_release_candidate_continuation_remains_update_execution() -> None:
    report = DialogueIntentClassifier().classify(UPDATE_CONTINUATION)

    assert report.primary_intent == "system_update_execution_request"
    assert report.update_request is True
    assert report.question_object == "system_update"


def test_update_execution_requests_github_but_still_obeys_host_capability_snapshot() -> None:
    snapshot = build_host_tool_capability_snapshot(
        {
            "tools": [
                {"name": "GitHub", "available": True},
                {"name": "web.run", "available": True},
            ]
        },
        env={},
    )
    policy = build_host_tool_turn_policy(
        user_text="Pracuj dalej aż aktualizacja będzie gotowa do scalenia.",
        detected_intent="system_update_execution_request",
        route="system_update",
        nlg_plan={"source_policy": "runtime_only"},
        host_tool_capabilities=snapshot,
    )

    assert "GitHub" in policy["requested_tools"]
    assert "GitHub" in policy["allowed_tools"]
    assert "GitHub" not in policy["required_tools"]
    violations = validate_tool_evidence_against_policy(
        [{"tool": "GitHub", "operation": "repository_read", "source_refs": [], "source_urls": []}],
        policy,
    )
    assert "tool_not_authorized_for_turn:GitHub" not in violations


def test_update_execution_does_not_force_github_when_host_reports_it_unavailable() -> None:
    snapshot = build_host_tool_capability_snapshot(
        {"tools": [{"name": "GitHub", "available": False}]},
        env={},
    )
    policy = build_host_tool_turn_policy(
        user_text="Pracuj dalej aż aktualizacja będzie gotowa do scalenia.",
        detected_intent="system_update_execution_request",
        route="system_update",
        nlg_plan={"source_policy": "runtime_only"},
        host_tool_capabilities=snapshot,
    )

    assert "GitHub" in policy["requested_tools"]
    assert "GitHub" not in policy["allowed_tools"]
    assert policy["required_tools"] == []
    assert "required_host_tool_unavailable:GitHub" not in validate_tool_evidence_against_policy([], policy)


def test_read_only_self_architecture_handler_satisfies_its_declared_contract() -> None:
    root = Path(__file__).resolve().parents[1]
    route = RouteRegistry().resolve("self_architecture_audit_request")
    result = SelfArchitectureAuditHandler().handle(
        "Audytuj architekturę Jaźni.",
        {
            "config": JaznConfig(root=root),
            "runtime_version": PACKAGE_VERSION_FULL,
            "required_components": route.required_components,
            "intent": "self_architecture_audit_request",
        },
    )

    assert set(route.required_components).issubset(set(result.satisfied_components))
    assert "Reflection grounding / grounded reflection store" in result.body
    assert result.data["grounded_reflection"]["attempted"] is False
    assert result.data["grounded_reflection_store"]["attempted"] is False
