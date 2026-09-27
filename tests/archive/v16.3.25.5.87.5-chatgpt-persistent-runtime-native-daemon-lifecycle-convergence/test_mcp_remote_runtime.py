from __future__ import annotations

from latka_jazn.mcp.remote_runtime import (
    classify_public_streamable_http_failover,
    preferred_verified_remote_transport,
)


def test_public_streamable_http_route_requires_all_independent_evidence() -> None:
    not_ready = classify_public_streamable_http_failover(
        endpoint_configured=True,
        auth_ready=True,
        protocol_compatible=True,
        health_payload={"status": "live", "gateway_live": True},
        readiness_payload={"status": "ready", "ready": True},
        host_connector_capability_available=False,
    )
    assert not_ready["remote_runtime_transport_available"] is False
    assert not_ready["reason_code"] == "chatgpt_connector_capability_not_verified"

    ready = classify_public_streamable_http_failover(
        endpoint_configured=True,
        auth_ready=True,
        protocol_compatible=True,
        health_payload={"status": "live", "gateway_live": True},
        readiness_payload={"status": "ready", "ready": True},
        host_connector_capability_available=True,
    )
    assert ready["remote_runtime_transport_available"] is True
    assert ready["execution_route"] == "remote_runtime"


def test_public_streamable_http_is_preferred_when_verified() -> None:
    public = {"remote_runtime_transport_available": True}
    tunnel = {"remote_runtime_transport_available": True}
    assert preferred_verified_remote_transport(
        public_streamable_http=public,
        secure_tunnel=tunnel,
    ) == "public_streamable_http"
