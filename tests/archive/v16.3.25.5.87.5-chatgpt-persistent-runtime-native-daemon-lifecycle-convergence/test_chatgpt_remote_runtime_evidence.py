from __future__ import annotations

import pytest

from latka_jazn.bootstrap.chatgpt_host_preflight_parse import (
    executor_observation_from_mapping,
)
from latka_jazn.core.chatgpt_host_executor_contract import (
    HostExecutionRoute,
    aggregate_host_executor_observations,
)


def _base() -> dict[str, object]:
    return {
        "surface": "ordinary_chat",
        "process_created": False,
        "error_class": "TransportTimeoutError",
    }


def test_preflight_rejects_bare_positive_remote_runtime_boolean() -> None:
    payload = {
        **_base(),
        "remote_runtime_transport_available": True,
    }
    with pytest.raises(
        ValueError,
        match="remote_runtime_transport_available_requires_verified_evidence",
    ):
        executor_observation_from_mapping(payload)


def test_preflight_derives_public_streamable_http_route_from_full_evidence() -> None:
    payload = {
        **_base(),
        "remote_runtime_evidence": {
            "transport": "public_streamable_http",
            "endpoint_configured": True,
            "auth_ready": True,
            "protocol_compatible": True,
            "health": {"status": "live", "gateway_live": True},
            "readiness": {"status": "ready", "ready": True},
            "host_connector_capability_available": True,
        },
    }

    observation = executor_observation_from_mapping(payload)
    assert observation.remote_runtime_transport_available is True
    assert observation.remote_runtime_transport == "public_streamable_http"
    assert observation.remote_runtime_reason_code == "public_streamable_http_remote_failover_ready"

    snapshot = aggregate_host_executor_observations([observation])
    assert snapshot.execution_route is HostExecutionRoute.REMOTE_RUNTIME
    assert snapshot.remote_runtime_transports == ("public_streamable_http",)


def test_preflight_derives_secure_tunnel_route_from_full_evidence() -> None:
    payload = {
        **_base(),
        "remote_runtime_evidence": {
            "transport": "openai_secure_mcp_tunnel",
            "runtime_status": {
                "process_running": True,
                "healthy": True,
                "ready": True,
            },
            "host_connector_capability_available": True,
        },
    }

    observation = executor_observation_from_mapping(payload)
    assert observation.remote_runtime_transport_available is True
    assert observation.remote_runtime_transport == "openai_secure_mcp_tunnel"
    assert observation.remote_runtime_reason_code == "secure_mcp_remote_failover_ready"


def test_preflight_keeps_public_remote_route_unavailable_without_host_capability() -> None:
    payload = {
        **_base(),
        "remote_runtime_evidence": {
            "transport": "public_streamable_http",
            "endpoint_configured": True,
            "auth_ready": True,
            "protocol_compatible": True,
            "health": {"status": "live", "gateway_live": True},
            "readiness": {"status": "ready", "ready": True},
            "host_connector_capability_available": False,
        },
    }

    observation = executor_observation_from_mapping(payload)
    assert observation.remote_runtime_transport_available is False
    assert observation.remote_runtime_transport == "public_streamable_http"
    assert observation.remote_runtime_reason_code == "chatgpt_connector_capability_not_verified"


def test_preflight_rejects_remote_declaration_that_conflicts_with_evidence() -> None:
    payload = {
        **_base(),
        "remote_runtime_transport_available": True,
        "remote_runtime_evidence": {
            "transport": "openai_secure_mcp_tunnel",
            "runtime_status": {
                "process_running": True,
                "healthy": False,
                "ready": True,
            },
            "host_connector_capability_available": True,
        },
    }

    with pytest.raises(
        ValueError,
        match="remote_runtime_transport_declaration_conflicts_with_verified_evidence",
    ):
        executor_observation_from_mapping(payload)
