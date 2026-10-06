from __future__ import annotations

from pathlib import Path

from latka_jazn.core.turn_diagnostics import (
    FailureKind,
    FallbackDecision,
    FallbackKind,
    TurnDiagnosticTrace,
    TurnStage,
)
from latka_jazn.core.turn_execution import TurnExecutionContext


def test_turn_diagnostic_trace_orders_events_and_redacts_private_attributes() -> None:
    trace = TurnDiagnosticTrace.create(
        session_id="session-1",
        request_id="request-1",
        turn_id="turn-1",
        trace_id="trace-1",
    )
    trace.record_event(
        stage=TurnStage.CONTEXT,
        component="ContextCoordinator",
        event_type="context_ready",
        outcome="ok",
        attributes={
            "user_text": "private message",
            "safe_count": 2,
            "nested": {"memory_excerpt": "secret", "status": "ready"},
        },
    )
    trace.record_event(
        stage=TurnStage.ROUTING,
        component="RouteRegistry",
        event_type="route_ready",
        outcome="ok",
    )

    payload = trace.to_dict()
    assert [item["seq"] for item in payload["events"]] == [1, 2]
    assert payload["events"][0]["attributes"]["user_text"] == "<redacted>"
    assert payload["events"][0]["attributes"]["nested"]["memory_excerpt"] == "<redacted>"
    assert payload["events"][0]["attributes"]["nested"]["status"] == "ready"
    assert payload["diagnostic_id"].startswith("JAZN-TURN-")


def test_turn_diagnostic_trace_preserves_typed_fallback_lineage() -> None:
    trace = TurnDiagnosticTrace.create(
        session_id="session-1",
        request_id="request-1",
        turn_id="turn-1",
        trace_id="trace-1",
    )
    trace.bind_route(
        intent="ordinary_conversation",
        route="ordinary_dialogue",
        handler="OrdinaryDialogueHandler",
    )
    decision = FallbackDecision.build(
        kind=FallbackKind.EXTERNAL_CAPABILITY_REQUIRED,
        origin_stage=TurnStage.MODEL,
        origin_component="ModelGuidedResponseSynthesizer",
        reason_code="MODEL_GUIDED_SPEECH_REQUIRED",
        from_route="ordinary_dialogue",
        to_route="host_model_phase2",
        recoverable=True,
        required_capability="host_model",
        attempt=1,
    )
    trace.record_fallback(decision)

    payload = trace.to_dict()
    assert payload["fallback"]["kind"] == "EXTERNAL_CAPABILITY_REQUIRED"
    assert payload["fallback"]["from_route"] == "ordinary_dialogue"
    assert payload["fallback"]["to_route"] == "host_model_phase2"
    assert payload["fallback"]["required_capability"] == "host_model"


def test_turn_execution_context_contains_one_diagnostic_root(tmp_path: Path) -> None:
    ctx = TurnExecutionContext.create(
        request_id="req",
        turn_id="turn",
        session_id="session",
        trace_id="trace",
        timeout_seconds=5.0,
        audit_db_path=tmp_path / "runtime_audit.sqlite3",
    )
    ctx.record_diagnostic_event(
        stage=TurnStage.ROUTING,
        component="RouteRegistry",
        event_type="route_bound",
        outcome="selected",
    )
    ctx.finalize_diagnostics(outcome="completed")

    snapshot = ctx.snapshot()
    diagnostic = snapshot["turn_diagnostics"]
    assert diagnostic["request_id"] == "req"
    assert diagnostic["turn_id"] == "turn"
    assert diagnostic["trace_id"] == "trace"
    assert diagnostic["final_outcome"] == "completed"
    assert diagnostic["event_count"] >= 3


def test_cancel_records_typed_failure_without_raw_reason_leak(tmp_path: Path) -> None:
    ctx = TurnExecutionContext.create(
        request_id="req-cancel",
        session_id="session",
        timeout_seconds=5.0,
        audit_db_path=tmp_path / "runtime_audit.sqlite3",
    )
    ctx.cancel(reason="private cancellation details", error_code="execution_timeout")
    diagnostic = ctx.diagnostic_snapshot()

    assert diagnostic["failure_kind"] == FailureKind.CANCELLED.value
    assert diagnostic["failure_reason_code"] == "execution_timeout"
    failure_events = [
        item for item in diagnostic["events"] if item["event_type"] == "failure"
    ]
    assert failure_events
    assert failure_events[-1]["attributes"]["cancellation_reason_present"] is True
    assert "private cancellation details" not in str(diagnostic)
