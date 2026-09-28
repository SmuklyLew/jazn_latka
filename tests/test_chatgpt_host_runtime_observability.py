from __future__ import annotations

from datetime import datetime, timezone

import pytest

from latka_jazn.bootstrap.chatgpt_host_preflight_parse import (
    executor_observation_from_mapping,
)
from latka_jazn.core.chatgpt_host_executor_aggregate_helpers import surface_payload
from latka_jazn.core.chatgpt_host_executor_contract import (
    HostCommandState,
    HostExecutorObservation,
    HostExecutorState,
    HostFilesystemState,
    classify_host_executor_observation,
)
from latka_jazn.mcp.remote_runtime import classify_public_streamable_http_failover
from latka_jazn.mcp.secure_tunnel import classify_remote_runtime_failover
from latka_jazn.version import PACKAGE_VERSION_FULL


_NOW = datetime(2026, 9, 28, 12, 0, tzinfo=timezone.utc)
_STAMP = _NOW.isoformat()


def _public_health() -> dict[str, object]:
    return {
        "status": "live",
        "gateway_live": True,
        "package_version": PACKAGE_VERSION_FULL,
        "gateway_instance_id": "gateway-observability-a",
        "observed_at_utc": _STAMP,
    }


def _public_readiness() -> dict[str, object]:
    return {
        "status": "ready",
        "ready": True,
        "package_version": PACKAGE_VERSION_FULL,
        "gateway_instance_id": "gateway-observability-a",
        "observed_at_utc": _STAMP,
        "runtime_instance_id": "daemon-observability-a",
        "runtime_version": PACKAGE_VERSION_FULL,
        "runtime_heartbeat_at_utc": _STAMP,
    }


def test_host_error_metadata_is_bounded_redacted_and_exported() -> None:
    secret_bearer = "very-secret-bearer-token-value"
    secret_api = "super-secret-api-value"
    secret_openai = "sk-proj-abcdefghijklmnopqrstuvwxyz0123456789"
    observation = HostExecutorObservation(
        process_created=False,
        error_class="ClientError",
        error_code="sandbox_provision_failed",
        error_message=(
            "host rejected process creation\n"
            f"Authorization: Bearer {secret_bearer}\n"
            f"api_key={secret_api}\n"
            f"provider={secret_openai}\n"
            + ("x" * 2048)
        ),
        host_request_id="req_executor_123",
        observed_at_utc=_STAMP,
    )

    assert observation.error_code == "sandbox_provision_failed"
    assert observation.host_request_id == "req_executor_123"
    assert observation.observed_at_utc == _STAMP
    assert observation.error_message is not None
    assert len(observation.error_message) <= 1024
    assert secret_bearer not in observation.error_message
    assert secret_api not in observation.error_message
    assert secret_openai not in observation.error_message
    assert "[REDACTED]" in observation.error_message

    decision = classify_host_executor_observation(observation)
    payload = surface_payload(observation, decision)
    assert payload["error_code"] == "sandbox_provision_failed"
    assert payload["host_request_id"] == "req_executor_123"
    assert payload["observed_at_utc"] == _STAMP
    assert payload["error_message"] == observation.error_message


def test_preprocess_client_error_semantics_remain_fail_closed() -> None:
    observation = executor_observation_from_mapping(
        {
            "surface": "ordinary_chat",
            "process_created": False,
            "error_class": "ClientError",
            "error_code": "executor_allocation_failed",
            "error_message": "host failed before process creation",
            "host_request_id": "req_fail_closed_1",
            "observed_at_utc": _STAMP,
        }
    )

    decision = classify_host_executor_observation(observation)
    assert decision.executor_state is HostExecutorState.HOST_EXECUTOR_UNAVAILABLE
    assert decision.command_state is HostCommandState.NOT_STARTED
    assert decision.filesystem_state is HostFilesystemState.UNKNOWN
    assert decision.package_state == "unknown"
    assert decision.runtime_state == "unverified"
    assert observation.remote_runtime_blockers == (
        "remote_runtime_evidence_missing",
    )


def test_public_remote_runtime_reports_all_blockers_without_changing_reason_code() -> None:
    health = _public_health()
    readiness = _public_readiness()
    readiness["ready"] = False
    readiness["runtime_instance_id"] = ""
    readiness["runtime_version"] = "wrong-version"
    result = classify_public_streamable_http_failover(
        endpoint_configured=True,
        auth_ready=False,
        protocol_compatible=True,
        health_payload=health,
        readiness_payload=readiness,
        host_connector_capability_available=False,
        now_utc=_NOW,
    )

    assert result["remote_runtime_transport_available"] is False
    assert result["reason_code"] == "public_mcp_auth_not_verified"
    assert result["blocking_checks"] == [
        "auth_ready",
        "runtime_ready",
        "runtime_binding_verified",
        "runtime_version_verified",
        "host_connector_capability_available",
    ]


def test_public_ready_route_has_no_blockers() -> None:
    result = classify_public_streamable_http_failover(
        endpoint_configured=True,
        auth_ready=True,
        protocol_compatible=True,
        health_payload=_public_health(),
        readiness_payload=_public_readiness(),
        host_connector_capability_available=True,
        now_utc=_NOW,
    )
    assert result["remote_runtime_transport_available"] is True
    assert result["blocking_checks"] == []


def test_secure_tunnel_reports_granular_runtime_and_connector_blockers() -> None:
    result = classify_remote_runtime_failover(
        {
            "process_running": True,
            "healthy": False,
            "ready": False,
            "runtime_instance_id": "",
            "runtime_version": "wrong-version",
            "observed_at_utc": _STAMP,
            "runtime_heartbeat_at_utc": _STAMP,
        },
        host_connector_capability_available=False,
        now_utc=_NOW,
    )

    assert result["remote_runtime_transport_available"] is False
    assert result["reason_code"] == "secure_mcp_tunnel_not_fully_ready"
    assert result["blocking_checks"] == [
        "healthy",
        "ready",
        "host_connector_capability_available",
        "runtime_binding_verified",
        "runtime_version_verified",
    ]


def test_preflight_preserves_classifier_blockers_and_safe_host_metadata() -> None:
    evidence = {
        "transport": "public_streamable_http",
        "endpoint_configured": True,
        "auth_ready": True,
        "protocol_compatible": True,
        "health": _public_health(),
        "readiness": _public_readiness(),
        "host_connector_capability_available": False,
    }
    observation = executor_observation_from_mapping(
        {
            "surface": "ordinary_chat",
            "process_created": False,
            "error_class": "TransportTimeoutError",
            "error_code": "transport_timeout",
            "error_message": "token=secret-value host timeout",
            "host_request_id": "req_timeout_123",
            "observed_at_utc": _STAMP,
            "remote_runtime_evidence": evidence,
        }
    )

    assert observation.remote_runtime_transport_available is False
    assert observation.remote_runtime_reason_code == (
        "chatgpt_connector_capability_not_verified"
    )
    assert observation.remote_runtime_blockers == (
        "host_connector_capability_available",
    )
    assert observation.error_code == "transport_timeout"
    assert observation.error_message is not None
    assert "secret-value" not in observation.error_message


def test_verified_route_rejects_conflicting_blocker_declaration() -> None:
    with pytest.raises(
        ValueError,
        match="remote_runtime_transport_available_conflicts_with_blocking_checks",
    ):
        HostExecutorObservation(
            process_created=False,
            remote_runtime_transport_available=True,
            remote_runtime_transport="public_streamable_http",
            remote_runtime_blockers=("evidence_fresh",),
        )


def test_preflight_rejects_non_string_diagnostic_metadata() -> None:
    with pytest.raises(ValueError, match="error_code_must_be_string"):
        executor_observation_from_mapping(
            {
                "surface": "ordinary_chat",
                "process_created": False,
                "error_code": 500,
            }
        )
