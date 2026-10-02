from __future__ import annotations

from datetime import datetime, timezone
from typing import cast

import pytest

from latka_jazn.bootstrap.chatgpt_host_preflight_parse import executor_observation_from_mapping
from latka_jazn.core.chatgpt_host_executor_contract import HostExecutionRoute, aggregate_host_executor_observations
from latka_jazn.version import PACKAGE_VERSION_FULL


def _base() -> dict[str, object]:
    return {"surface": "ordinary_chat", "process_created": False, "error_class": "TransportTimeoutError"}


def _stamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _public_evidence(*, connector: bool = True) -> dict[str, object]:
    stamp = _stamp()
    return {
        "transport": "public_streamable_http",
        "endpoint_configured": True,
        "auth_ready": True,
        "protocol_compatible": True,
        "health": {
            "status": "live", "gateway_live": True,
            "package_version": PACKAGE_VERSION_FULL,
            "gateway_instance_id": "gateway-preflight-a",
            "observed_at_utc": stamp,
        },
        "readiness": {
            "status": "ready", "ready": True,
            "package_version": PACKAGE_VERSION_FULL,
            "gateway_instance_id": "gateway-preflight-a",
            "observed_at_utc": stamp,
            "runtime_instance_id": "daemon-preflight-a",
            "runtime_version": PACKAGE_VERSION_FULL,
            "runtime_heartbeat_at_utc": stamp,
        },
        "host_connector_capability_available": connector,
    }


def _tunnel_evidence(*, healthy: bool = True, connector: bool = True) -> dict[str, object]:
    stamp = _stamp()
    return {
        "transport": "openai_secure_mcp_tunnel",
        "runtime_status": {
            "process_running": True, "healthy": healthy, "ready": True,
            "runtime_instance_id": "daemon-tunnel-preflight-a",
            "runtime_version": PACKAGE_VERSION_FULL,
            "observed_at_utc": stamp,
            "runtime_heartbeat_at_utc": stamp,
        },
        "host_connector_capability_available": connector,
    }


def test_preflight_rejects_bare_positive_remote_runtime_boolean() -> None:
    with pytest.raises(ValueError, match="remote_runtime_transport_available_requires_verified_evidence"):
        executor_observation_from_mapping({**_base(), "remote_runtime_transport_available": True})


def test_preflight_derives_public_streamable_http_route_from_full_evidence() -> None:
    observation = executor_observation_from_mapping({**_base(), "remote_runtime_evidence": _public_evidence()})
    assert observation.remote_runtime_transport_available is True
    assert observation.remote_runtime_transport == "public_streamable_http"
    assert observation.remote_runtime_reason_code == "public_streamable_http_remote_failover_ready"
    snapshot = aggregate_host_executor_observations([observation])
    assert snapshot.execution_route is HostExecutionRoute.REMOTE_RUNTIME
    assert snapshot.remote_runtime_transports == ("public_streamable_http",)


def test_preflight_derives_secure_tunnel_route_from_full_evidence() -> None:
    observation = executor_observation_from_mapping({**_base(), "remote_runtime_evidence": _tunnel_evidence()})
    assert observation.remote_runtime_transport_available is True
    assert observation.remote_runtime_transport == "openai_secure_mcp_tunnel"
    assert observation.remote_runtime_reason_code == "secure_mcp_remote_failover_ready"


def test_preflight_keeps_public_remote_route_unavailable_without_host_capability() -> None:
    observation = executor_observation_from_mapping({**_base(), "remote_runtime_evidence": _public_evidence(connector=False)})
    assert observation.remote_runtime_transport_available is False
    assert observation.remote_runtime_reason_code == "chatgpt_connector_capability_not_verified"


def test_preflight_keeps_structurally_valid_route_unavailable_without_instance_binding() -> None:
    evidence = _public_evidence()
    readiness = dict(cast(dict[str, object], evidence["readiness"]))
    readiness["runtime_instance_id"] = ""
    evidence["readiness"] = readiness
    observation = executor_observation_from_mapping({**_base(), "remote_runtime_evidence": evidence})
    assert observation.remote_runtime_transport_available is False
    assert observation.remote_runtime_reason_code == "public_mcp_runtime_binding_not_verified"


def test_preflight_rejects_remote_declaration_that_conflicts_with_evidence() -> None:
    with pytest.raises(ValueError, match="remote_runtime_transport_declaration_conflicts_with_verified_evidence"):
        executor_observation_from_mapping({
            **_base(),
            "remote_runtime_transport_available": True,
            "remote_runtime_evidence": _tunnel_evidence(healthy=False),
        })
