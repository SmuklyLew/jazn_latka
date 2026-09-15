from __future__ import annotations

from pathlib import Path
from typing import Any
import json
import uuid

import pytest

from latka_jazn.bridge.secure_host_runtime_gateway import (
    GatewayConfig,
    GatewayError,
    SecureHostRuntimeGateway,
)
from latka_jazn.mcp.task_resume import McpTaskResumeAdapter, TASK_EXTENSION_ID
from latka_jazn.runtime.capability_matrix import build_capability_matrix
from latka_jazn.runtime.operation_registry import OperationConflictError, OperationRegistry
from latka_jazn.runtime.resilience import (
    CircuitBreaker,
    CircuitOpenError,
    RetryBudget,
    RetryPolicy,
    TransportSupervisor,
)


class MutableClock:
    def __init__(self, value: float = 100.0) -> None:
        self.value = value

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


def test_retry_budget_is_aggregate_and_recovers_after_window() -> None:
    clock = MutableClock()
    budget = RetryBudget(allowed_retries=2, window_seconds=60.0, clock=clock)

    assert budget.consume() is True
    assert budget.consume() is True
    assert budget.consume() is False
    assert budget.snapshot().remaining == 0

    clock.advance(61.0)
    assert budget.consume() is True
    assert budget.snapshot().remaining == 1


def test_circuit_breaker_opens_half_opens_and_recovers_durably(tmp_path: Path) -> None:
    clock = MutableClock(1_000.0)
    state = tmp_path / "breaker.json"
    breaker = CircuitBreaker(
        "daemon",
        failure_threshold=2,
        recovery_timeout_seconds=5.0,
        state_path=state,
        wall_clock=clock,
    )

    breaker.acquire()
    breaker.record_failure("timeout-1")
    breaker.acquire()
    breaker.record_failure("timeout-2")
    assert breaker.snapshot().state == "open"
    with pytest.raises(CircuitOpenError):
        breaker.acquire()

    clock.advance(5.1)
    breaker.acquire()
    assert breaker.snapshot().state == "half_open"
    breaker.record_success()
    assert breaker.snapshot().state == "closed"

    reloaded = CircuitBreaker(
        "daemon",
        failure_threshold=2,
        recovery_timeout_seconds=5.0,
        state_path=state,
        wall_clock=clock,
    )
    assert reloaded.snapshot().state == "closed"
    assert reloaded.snapshot().consecutive_failures == 0


def test_transport_supervisor_never_retries_ambiguous_side_effect() -> None:
    attempts: list[int] = []
    supervisor = TransportSupervisor(
        breaker=CircuitBreaker("submit", failure_threshold=5, recovery_timeout_seconds=1.0),
        retry_budget=RetryBudget(allowed_retries=10, window_seconds=60.0),
        retry_policy=RetryPolicy(max_attempts=4, base_delay_seconds=0.0, max_delay_seconds=0.0),
        sleep=lambda _seconds: None,
        random_unit=lambda: 0.0,
        transient_error=lambda _exc: True,
    )

    def fail() -> None:
        attempts.append(1)
        raise TimeoutError("injected")

    with pytest.raises(TimeoutError):
        supervisor.execute(fail, retry_safe=False)
    assert len(attempts) == 1


def test_transport_supervisor_retries_safe_read_once_then_succeeds() -> None:
    attempts: list[int] = []
    supervisor = TransportSupervisor(
        breaker=CircuitBreaker("poll", failure_threshold=5, recovery_timeout_seconds=1.0),
        retry_budget=RetryBudget(allowed_retries=10, window_seconds=60.0),
        retry_policy=RetryPolicy(max_attempts=2, base_delay_seconds=0.0, max_delay_seconds=0.0),
        sleep=lambda _seconds: None,
        random_unit=lambda: 0.0,
        transient_error=lambda _exc: True,
    )

    def flaky() -> str:
        attempts.append(1)
        if len(attempts) == 1:
            raise TimeoutError("injected")
        return "ok"

    assert supervisor.execute(flaky, retry_safe=True) == "ok"
    assert len(attempts) == 2


def test_operation_registry_survives_restart_without_storing_payload(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir()
    monkeypatch.setenv("JAZN_RUNTIME_WORKSPACE_DIR", str(tmp_path / "workspace"))
    registry = OperationRegistry(runtime_root)
    operation_id = "op-" + uuid.uuid4().hex
    secret = "private-user-message-that-must-not-be-stored"

    claimed = registry.claim(
        operation_id=operation_id,
        operation_kind="chat_turn",
        payload={"message": secret, "request_id": operation_id},
    )
    assert claimed.state == "registered"
    registry.transition(operation_id, "outcome_unknown", last_error="TransportTimeoutError")

    files = list((tmp_path / "workspace" / "operations").glob("*.json"))
    assert len(files) == 1
    assert secret not in files[0].read_text(encoding="utf-8")

    restarted = OperationRegistry(runtime_root)
    recovered = restarted.get(operation_id)
    assert recovered is not None
    assert recovered.state == "outcome_unknown"
    assert recovered.last_error == "TransportTimeoutError"

    with pytest.raises(OperationConflictError):
        restarted.claim(
            operation_id=operation_id,
            operation_kind="chat_turn",
            payload={"message": "different", "request_id": operation_id},
        )


def test_gateway_timeout_records_unknown_outcome_and_second_call_only_polls(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir()
    monkeypatch.setenv("JAZN_RUNTIME_WORKSPACE_DIR", str(tmp_path / "workspace"))
    gateway = SecureHostRuntimeGateway(
        GatewayConfig(
            runtime_root=runtime_root,
            daemon_token="test-token",
            transport_retry_attempts=1,
            transport_circuit_failure_threshold=10,
        )
    )
    request_id = str(uuid.uuid4())
    methods: list[str] = []

    def first(method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        methods.append(method)
        raise GatewayError("daemon_unavailable:TimeoutError")

    monkeypatch.setattr(gateway, "_http_json_once", first)
    response = gateway.chat("hello", session_id="s", request_id=request_id)
    assert response["chatgpt_host_presentation"]["action"] == "poll_runtime"
    assert gateway.operations.get(request_id).state == "outcome_unknown"  # type: ignore[union-attr]
    assert methods == ["POST"]

    def resumed(method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        methods.append(method)
        assert method == "GET"
        assert "/chat-result?" in path
        return {"accepted": True, "done": False, "status": "running", "request_id": request_id}

    monkeypatch.setattr(gateway, "_http_json_once", resumed)
    second = gateway.chat("hello", session_id="s", request_id=request_id)
    assert second["chatgpt_host_presentation"]["action"] == "poll_runtime"
    assert methods == ["POST", "GET"]


def _pending_tool_result(request_id: str) -> dict[str, Any]:
    return {
        "content": [{"type": "text", "text": "pending"}],
        "structuredContent": {
            "ok": True,
            "action": "poll_runtime",
            "daemon_request_id": request_id,
            "request_id": request_id,
        },
        "_meta": {},
        "isError": False,
    }


def test_mcp_task_handle_is_durable_and_poll_resumes_same_daemon_request(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir()
    monkeypatch.setenv("JAZN_RUNTIME_WORKSPACE_DIR", str(tmp_path / "workspace"))
    request_id = str(uuid.uuid4())

    class FakeGateway:
        def result(self, request_id: str) -> dict[str, Any]:
            assert request_id == outer_request_id
            return {}

    outer_request_id = request_id
    adapter = McpTaskResumeAdapter(root=runtime_root, gateway=FakeGateway())
    created = adapter.create_from_pending_result(_pending_tool_result(request_id))
    assert created is not None
    assert created["resultType"] == "task"
    assert created["status"] == "working"
    task_id = created["taskId"]

    calls: list[str] = []

    def pending_resume(**kwargs: Any) -> dict[str, Any]:
        calls.append(str(kwargs["daemon_request_id"]))
        return _pending_tool_result(request_id)

    monkeypatch.setattr(
        "latka_jazn.mcp.task_resume.jazn_resume_visible_reply.run",
        pending_resume,
    )
    working = adapter.get(task_id)
    assert working["status"] == "working"
    assert calls == [request_id]

    completed_tool = {
        "content": [{"type": "text", "text": "done"}],
        "structuredContent": {"ok": True, "action": "display_exact", "final_visible_text": "done"},
        "_meta": {},
        "isError": False,
    }

    def complete_resume(**kwargs: Any) -> dict[str, Any]:
        calls.append(str(kwargs["daemon_request_id"]))
        return completed_tool

    monkeypatch.setattr(
        "latka_jazn.mcp.task_resume.jazn_resume_visible_reply.run",
        complete_resume,
    )
    restarted = McpTaskResumeAdapter(root=runtime_root, gateway=FakeGateway())
    completed = restarted.get(task_id)
    assert completed["status"] == "completed"
    assert completed["result"] == completed_tool
    assert calls == [request_id, request_id]


def test_capability_matrix_keeps_system_only_dialogue_ready(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir()
    monkeypatch.setenv("JAZN_RUNTIME_WORKSPACE_DIR", str(tmp_path / "workspace"))
    monkeypatch.setenv("JAZN_MEMORY_MODE", "optional")
    monkeypatch.delenv("JAZN_MEMORY_ROOT", raising=False)

    matrix = build_capability_matrix(
        runtime_root,
        gateway_status={
            "gateway_ok": True,
            "daemon_reachable": True,
            "daemon_auth_configured": True,
            "transport": "loopback_only_authenticated",
            "daemon": {"runtime_core_ready": True, "host_finalization_ready": True},
        },
    )

    assert matrix["conversation_ready"] is True
    assert matrix["ordinary_dialogue_allowed"] is True
    assert matrix["components"]["persistent_memory"]["available"] is False
    assert matrix["components"]["recall"]["available"] is False
    assert matrix["components"]["mcp_tasks"]["available"] is True
    assert TASK_EXTENSION_ID in matrix["components"]["mcp_tasks"]["reason"]
