from __future__ import annotations

from latka_jazn.mcp.turn_runtime_adapter import McpTurnRuntimeAdapter
from latka_jazn.runtime.turn_runtime import (
    ExecutionRoute,
    ProfessionalTurnRuntime,
    RouteEvidence,
    TurnIdentity,
    TurnPhase,
    valid_w3c_trace_id,
)


def _poll_result(request_id: str) -> dict:
    return {
        "content": [{"type": "text", "text": "pending"}],
        "structuredContent": {
            "ok": True,
            "action": "poll_runtime",
            "request_id": request_id,
            "daemon_request_id": request_id,
            "must_not_resubmit_user_message": True,
        },
        "_meta": {},
        "isError": False,
    }


def test_remote_runtime_is_preferred_only_when_fully_verified() -> None:
    runtime = ProfessionalTurnRuntime()
    decision = runtime.choose_route(
        RouteEvidence(
            local_executor_available=True,
            remote_process_running=True,
            remote_healthy=True,
            remote_ready=True,
            host_connector_capability_available=True,
        )
    )
    assert decision.execution_route is ExecutionRoute.REMOTE_RUNTIME
    assert decision.remote_runtime_verified is True

    no_connector = runtime.choose_route(
        RouteEvidence(
            local_executor_available=True,
            remote_process_running=True,
            remote_healthy=True,
            remote_ready=True,
            host_connector_capability_available=False,
        )
    )
    assert no_connector.execution_route is ExecutionRoute.LOCAL_EXECUTOR


def test_route_falls_back_to_handoff_then_fail_closed() -> None:
    runtime = ProfessionalTurnRuntime()
    handoff = runtime.choose_route(RouteEvidence(host_handoff_available=True))
    assert handoff.execution_route is ExecutionRoute.HOST_HANDOFF
    unavailable = runtime.choose_route(RouteEvidence())
    assert unavailable.execution_route is ExecutionRoute.UNAVAILABLE
    assert unavailable.executable is False


def test_turn_identity_is_stable_and_w3c_compatible() -> None:
    first = TurnIdentity.build(request_id="req-77", message="Hej", session_id="chatgpt-main")
    second = TurnIdentity.build(request_id="req-77", message="Hej", session_id="chatgpt-main")
    assert first == second
    assert valid_w3c_trace_id(first.transport_trace_id)
    assert first.traceparent.startswith("00-")
    assert len(first.traceparent.split("-")) == 4


def test_phase_transition_table_rejects_terminal_reentry() -> None:
    runtime = ProfessionalTurnRuntime()
    assert runtime.transition_allowed(TurnPhase.SUBMITTED, TurnPhase.POLLING)
    assert runtime.transition_allowed(TurnPhase.POLLING, TurnPhase.ACCEPTED_VISIBLE)
    assert not runtime.transition_allowed(TurnPhase.ACCEPTED_VISIBLE, TurnPhase.POLLING)


def test_poll_runtime_requires_same_request_id_and_no_replay_guard() -> None:
    runtime = ProfessionalTurnRuntime()
    identity = TurnIdentity.build(request_id="req-1", message="hello")
    directive = runtime.classify_tool_result(
        tool_name="jazn_generate_visible_reply",
        result=_poll_result("req-1"),
        identity=identity,
    )
    assert directive.phase is TurnPhase.POLLING
    assert directive.must_not_resubmit_user_message is True

    mismatched = runtime.fail_closed_tool_result("fixture")
    assert mismatched["structuredContent"]["action"] == "host_diagnostic"


def test_generate_then_finalize_requires_bound_contract() -> None:
    runtime = ProfessionalTurnRuntime()
    identity = TurnIdentity.build(request_id="req-2", message="hello")
    result = {
        "content": [],
        "structuredContent": {
            "ok": True,
            "action": "generate_then_finalize",
            "daemon_request_id": "req-2",
            "continuation_token": "jct1.abc",
            "host_request_contract_hash": "a" * 64,
            "finalization_tool": "jazn_finalize_reply",
            "must_not_display_intermediate": True,
        },
        "_meta": {},
        "isError": False,
    }
    directive = runtime.classify_tool_result(
        tool_name="jazn_generate_visible_reply",
        result=result,
        identity=identity,
    )
    assert directive.phase is TurnPhase.AWAITING_HOST_FINALIZATION
    assert directive.host_request_contract_hash == "a" * 64


def test_display_exact_is_the_only_visible_success_action() -> None:
    runtime = ProfessionalTurnRuntime()
    identity = TurnIdentity.build(request_id="req-3")
    result = {
        "content": [{"type": "text", "text": "visible"}],
        "structuredContent": {
            "ok": True,
            "action": "display_exact",
            "final_visible_text": "visible",
            "must_display_exactly": True,
            "turn_id": "turn-1",
            "trace_id": "trace-1",
        },
        "_meta": {},
        "isError": False,
    }
    decorated = runtime.decorate_tool_result(
        tool_name="jazn_finalize_reply",
        result=result,
        identity=identity,
    )
    assert decorated["_meta"]["io.jazn/turn-runtime"]["directive"]["phase"] == "accepted_visible"


def test_mcp_adapter_converts_request_mismatch_to_host_diagnostic() -> None:
    adapter = McpTurnRuntimeAdapter()
    request = {
        "jsonrpc": "2.0",
        "id": 7,
        "method": "tools/call",
        "params": {
            "name": "jazn_generate_visible_reply",
            "arguments": {"message": "hello", "request_id": "req-a"},
        },
    }
    response = {
        "jsonrpc": "2.0",
        "id": 7,
        "result": _poll_result("req-b"),
    }
    decorated = adapter.decorate_call_response(request, response)
    assert decorated is not None
    assert decorated["result"]["isError"] is True
    assert decorated["result"]["structuredContent"]["action"] == "host_diagnostic"
    assert "daemon_request_id_mismatch" in decorated["result"]["structuredContent"]["reason"]


def test_mcp_adapter_attaches_retry_and_trace_metadata() -> None:
    adapter = McpTurnRuntimeAdapter()
    request = {
        "jsonrpc": "2.0",
        "id": 8,
        "method": "tools/call",
        "params": {
            "name": "jazn_generate_visible_reply",
            "arguments": {"message": "hello", "request_id": "req-c"},
        },
    }
    response = {"jsonrpc": "2.0", "id": 8, "result": _poll_result("req-c")}
    decorated = adapter.decorate_call_response(request, response)
    assert decorated is not None
    metadata = decorated["result"]["_meta"]["io.jazn/turn-runtime"]
    assert metadata["identity"]["request_id"] == "req-c"
    assert metadata["retry"]["automatic_retry_allowed"] is False
    assert metadata["retry"]["resume_same_request_id"] is True
