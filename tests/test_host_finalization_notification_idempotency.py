from __future__ import annotations

"""Regression coverage for distinct daemon finalization notifications."""

from pathlib import Path
from typing import Any

import pytest

from latka_jazn.bridge.secure_host_runtime_gateway import (
    GatewayError,
    SecureHostRuntimeGateway,
)
from latka_jazn.runtime.operation_registry import OperationRegistry


REQUEST_ID = "finalization-unique-request-1"


def _pending(*, request_id: str = REQUEST_ID, turn_id: str = "turn-1") -> dict[str, Any]:
    return {
        "binding": {
            "daemon_request_id": request_id,
            "turn_id": turn_id,
            "trace_id": "trace-1",
        },
        "request_contract_hash": "a" * 64,
    }


def _gateway(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> SecureHostRuntimeGateway:
    monkeypatch.setenv("JAZN_RUNTIME_WORKSPACE_DIR", str(tmp_path / "workspace"))
    gateway = object.__new__(SecureHostRuntimeGateway)
    gateway.operations = OperationRegistry(tmp_path)
    return gateway


def test_regeneration_then_acceptance_are_distinct_operations(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    gateway = _gateway(monkeypatch, tmp_path)
    payloads: list[dict[str, Any]] = []

    def daemon(method: str, path: str, payload: dict[str, Any], *, retry_safe: bool) -> dict[str, Any]:
        assert (method, path, retry_safe) == ("POST", "/chat-finalization", False)
        payloads.append(dict(payload))
        return {"ok": True, "status": "noted"}

    monkeypatch.setattr(gateway, "_http_json", daemon)
    first = gateway.note_host_finalization(_pending(), outcome="regeneration_requested", reason="missing_intent")
    second = gateway.note_host_finalization(_pending(), outcome="accepted", reason="commit_accepted", terminal=True)

    assert first["ok"] and second["ok"]
    assert [p["outcome"] for p in payloads] == ["regeneration_requested", "accepted"]
    assert {p["request_id"] for p in payloads} == {REQUEST_ID}
    operations = [gateway.operations._read_path(p) for p in gateway.operations.root.glob("*.json")]
    assert len(operations) == 2
    assert all(op is not None and op.state == "completed" for op in operations)
    assert len({op.operation_id for op in operations if op is not None}) == 2


def test_identical_notification_replay_does_not_post_twice(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    gateway = _gateway(monkeypatch, tmp_path)
    calls: list[dict[str, Any]] = []

    def daemon(method: str, path: str, payload: dict[str, Any], *, retry_safe: bool) -> dict[str, Any]:
        calls.append(dict(payload))
        return {"ok": True}

    monkeypatch.setattr(gateway, "_http_json", daemon)
    assert gateway.note_host_finalization(_pending(), outcome="accepted", reason="commit_accepted")["ok"]
    replay = gateway.note_host_finalization(_pending(), outcome="accepted", reason="commit_accepted")

    assert replay == {"ok": True, "replayed_operation": True, "request_id": REQUEST_ID}
    assert len(calls) == 1
    assert len(list(gateway.operations.root.glob("*.json"))) == 1


def test_lost_ack_retries_same_event_after_gateway_restart(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    gateway = _gateway(monkeypatch, tmp_path)
    calls: list[dict[str, Any]] = []

    def daemon(method: str, path: str, payload: dict[str, Any], *, retry_safe: bool) -> dict[str, Any]:
        calls.append(dict(payload))
        if len(calls) == 1:
            # The server applied the notification but its ACK was lost.
            raise GatewayError("daemon_unavailable:TimeoutError")
        return {"ok": True, "status": "already_applied"}

    monkeypatch.setattr(gateway, "_http_json", daemon)
    with pytest.raises(GatewayError, match="daemon_unavailable:TimeoutError"):
        gateway.note_host_finalization(_pending(), outcome="accepted", reason="commit_accepted")
    op_path = next(gateway.operations.root.glob("*.json"))
    assert gateway.operations._read_path(op_path).state == "outcome_unknown"  # type: ignore[union-attr]

    restarted = _gateway(monkeypatch, tmp_path)
    monkeypatch.setattr(restarted, "_http_json", daemon)
    assert restarted.note_host_finalization(_pending(), outcome="accepted", reason="commit_accepted")["ok"]
    assert len(calls) == 2
    assert len(list(gateway.operations.root.glob("*.json"))) == 1
    assert restarted.operations._read_path(op_path).state == "completed"  # type: ignore[union-attr]


def test_distinct_turns_do_not_share_notification_operation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    gateway = _gateway(monkeypatch, tmp_path)
    monkeypatch.setattr(gateway, "_http_json", lambda *args, **kwargs: {"ok": True})
    for rid in ("rid-one", "rid-two"):
        gateway.note_host_finalization(_pending(request_id=rid), outcome="accepted", reason="commit_accepted")
    assert len(list(gateway.operations.root.glob("*.json"))) == 2


def test_repeated_reason_change_is_new_event_not_registry_conflict(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    gateway = _gateway(monkeypatch, tmp_path)
    calls: list[dict[str, Any]] = []

    def daemon(method: str, path: str, payload: dict[str, Any], *, retry_safe: bool) -> dict[str, Any]:
        calls.append(dict(payload))
        return {"ok": True}

    monkeypatch.setattr(gateway, "_http_json", daemon)
    gateway.note_host_finalization(_pending(), outcome="regeneration_requested", reason="needs_context")
    gateway.note_host_finalization(_pending(), outcome="regeneration_requested", reason="needs_format")
    assert len(calls) == 2
    assert len(list(gateway.operations.root.glob("*.json"))) == 2
