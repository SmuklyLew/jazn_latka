from __future__ import annotations

from latka_jazn.core.turn_execution import TurnExecutionContext


def test_turn_execution_exposes_explicit_trace_and_stage_spans() -> None:
    context = TurnExecutionContext.create(
        request_id="request-1",
        turn_id="turn-1",
        trace_id="trace-1",
        session_id="session-1",
        timeout_seconds=30,
    )
    with context.stage("synthesis"):
        pass
    context.finalize_total(status="completed")

    snapshot = context.snapshot()
    assert snapshot["request_id"] == "request-1"
    assert snapshot["turn_id"] == "turn-1"
    assert snapshot["trace_id"] == "trace-1"
    assert len(snapshot["root_span_id"]) == 16
    synthesis = snapshot["stages"]["synthesis"]
    assert synthesis["trace_id"] == "trace-1"
    assert synthesis["parent_span_id"] == snapshot["root_span_id"]
    assert len(synthesis["span_id"]) == 16


def test_trace_defaults_to_request_id_for_backward_compatibility() -> None:
    context = TurnExecutionContext.create(
        request_id="request-compat",
        turn_id="turn-compat",
        session_id="session-compat",
        timeout_seconds=30,
    )
    assert context.trace_id == "request-compat"
    assert context.snapshot()["trace_id"] == "request-compat"
