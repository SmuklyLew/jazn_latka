from __future__ import annotations

from datetime import datetime, timedelta, timezone
from latka_jazn.mcp.remote_runtime import classify_public_streamable_http_failover, preferred_verified_remote_transport
from latka_jazn.version import PACKAGE_VERSION_FULL

NOW = datetime(2026, 9, 27, 12, 0, 0, tzinfo=timezone.utc)


def _evidence(now: datetime = NOW, *, gateway: str = "gateway-a", runtime_version: str = PACKAGE_VERSION_FULL):
    stamp = now.isoformat()
    return (
        {"status":"live","gateway_live":True,"package_version":PACKAGE_VERSION_FULL,"gateway_instance_id":gateway,"observed_at_utc":stamp},
        {"status":"ready","ready":True,"package_version":PACKAGE_VERSION_FULL,"gateway_instance_id":gateway,"observed_at_utc":stamp,"runtime_instance_id":"daemon-a","runtime_version":runtime_version,"runtime_heartbeat_at_utc":stamp},
    )


def test_public_streamable_http_route_requires_all_independent_evidence() -> None:
    health, readiness = _evidence()
    blocked = classify_public_streamable_http_failover(
        endpoint_configured=True, auth_ready=True, protocol_compatible=True,
        health_payload=health, readiness_payload=readiness,
        host_connector_capability_available=False, now_utc=NOW,
    )
    assert blocked["reason_code"] == "chatgpt_connector_capability_not_verified"
    ready = classify_public_streamable_http_failover(
        endpoint_configured=True, auth_ready=True, protocol_compatible=True,
        health_payload=health, readiness_payload=readiness,
        host_connector_capability_available=True, now_utc=NOW,
    )
    assert ready["remote_runtime_transport_available"] is True
    assert ready["gateway_binding_verified"] is True
    assert ready["runtime_binding_verified"] is True
    assert ready["evidence_fresh"] is True


def test_public_streamable_http_rejects_cross_gateway_binding() -> None:
    health, readiness = _evidence()
    readiness["gateway_instance_id"] = "gateway-b"
    result = classify_public_streamable_http_failover(
        endpoint_configured=True, auth_ready=True, protocol_compatible=True,
        health_payload=health, readiness_payload=readiness,
        host_connector_capability_available=True, now_utc=NOW,
    )
    assert result["reason_code"] == "public_mcp_gateway_binding_not_verified"


def test_public_streamable_http_rejects_wrong_runtime_version() -> None:
    health, readiness = _evidence(runtime_version="old-runtime")
    result = classify_public_streamable_http_failover(
        endpoint_configured=True, auth_ready=True, protocol_compatible=True,
        health_payload=health, readiness_payload=readiness,
        host_connector_capability_available=True, now_utc=NOW,
    )
    assert result["reason_code"] == "public_mcp_runtime_version_mismatch"


def test_public_streamable_http_rejects_stale_evidence() -> None:
    health, readiness = _evidence(NOW - timedelta(minutes=10))
    result = classify_public_streamable_http_failover(
        endpoint_configured=True, auth_ready=True, protocol_compatible=True,
        health_payload=health, readiness_payload=readiness,
        host_connector_capability_available=True, now_utc=NOW,
    )
    assert result["reason_code"] == "remote_runtime_evidence_stale"


def test_public_streamable_http_is_preferred_when_verified() -> None:
    assert preferred_verified_remote_transport(
        public_streamable_http={"remote_runtime_transport_available":True},
        secure_tunnel={"remote_runtime_transport_available":True},
    ) == "public_streamable_http"
