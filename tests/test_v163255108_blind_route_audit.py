from __future__ import annotations

from pathlib import Path

from latka_jazn.core.blind_route_detector import BlindRouteDetector
from latka_jazn.core.route_graph_contract import audit_route_graph
from latka_jazn.core.turn_diagnostics import FallbackDecision, FallbackKind, TurnStage


def test_route_graph_audit_is_green_for_current_registered_graph() -> None:
    root = Path(__file__).resolve().parents[1]
    audit = audit_route_graph(root)

    assert audit["ok"] is True, audit
    assert audit["unresolved_intents"] == []
    assert audit["routes_without_handlers"] == []
    assert audit["unreachable_handlers"] == []
    assert audit["required_components_without_owner"] == []
    assert audit["duplicate_canonical_owners"] == []
    assert audit["anonymous_fallbacks"] == []
    assert set(audit["compatibility_allowlist"]) == {
        "FallbackHandler",
        "FileOperationHandler",
    }
    assert "recovery boundary" in audit["compatibility_allowlist"]["FallbackHandler"]
    assert "legacy compatibility-only" in audit["compatibility_allowlist"]["FileOperationHandler"]


def test_blind_route_detector_reports_missing_required_component() -> None:
    detector = BlindRouteDetector()
    findings = detector.detect(
        intent="self_state_question",
        route="self_state",
        handler_name="SelfStateHandler",
        required_components=("operational_state", "truth_boundary"),
        missing_components=("operational_state",),
        dispatch_report={"status": "ok"},
        validation={
            "accepted": False,
            "mismatch_reason": "missing_components",
            "missing_required_components": ["operational_state"],
        },
    )

    assert any(
        item.code == "BLIND_ROUTE_REQUIRED_COMPONENT_MISSING"
        for item in findings
    )


def test_blind_route_detector_rejects_anonymous_dispatch_fallback() -> None:
    detector = BlindRouteDetector()
    findings = detector.detect(
        intent="unknown_intent",
        route="fallback",
        handler_name="FallbackHandler",
        dispatch_report={"status": "fallback_selected"},
        validation={"accepted": True},
        fallback=None,
    )
    codes = {item.code for item in findings}
    assert "BLIND_ROUTE_HANDLER_DISPATCH_DEGRADED" in codes
    assert "BLIND_ROUTE_ANONYMOUS_FALLBACK" in codes


def test_typed_fallback_prevents_anonymous_fallback_finding() -> None:
    detector = BlindRouteDetector()
    fallback = FallbackDecision.build(
        kind=FallbackKind.RECOVERABLE_FALLBACK,
        origin_stage=TurnStage.ROUTING,
        origin_component="RouteHandlerDispatcher.dispatch",
        reason_code="ROUTE_HANDLER_UNRESOLVED",
        from_route="unknown_route",
        to_route="fallback",
        recoverable=True,
    )
    findings = detector.detect(
        intent="unknown_intent",
        route="fallback",
        handler_name="FallbackHandler",
        dispatch_report={"status": "fallback_selected"},
        validation={"accepted": True},
        fallback=fallback,
    )
    assert "BLIND_ROUTE_ANONYMOUS_FALLBACK" not in {
        item.code for item in findings
    }
