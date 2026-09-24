from __future__ import annotations

"""Evidence-only classifiers for executor-independent MCP runtime routes."""

from dataclasses import asdict, dataclass
from typing import Any, Mapping

from latka_jazn.runtime.turn_runtime import RemoteTransport
from latka_jazn.version import PACKAGE_VERSION_FULL, schema_version

SCHEMA_VERSION = schema_version("mcp_remote_runtime")


@dataclass(frozen=True, slots=True)
class PublicStreamableHttpEvidence:
    endpoint_configured: bool
    auth_ready: bool
    protocol_compatible: bool
    gateway_live: bool
    runtime_ready: bool
    host_connector_capability_available: bool

    @property
    def route_ready(self) -> bool:
        return all(
            (
                self.endpoint_configured,
                self.auth_ready,
                self.protocol_compatible,
                self.gateway_live,
                self.runtime_ready,
                self.host_connector_capability_available,
            )
        )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.update(
            {
                "schema_version": SCHEMA_VERSION,
                "package_version": PACKAGE_VERSION_FULL,
                "remote_transport": RemoteTransport.PUBLIC_STREAMABLE_HTTP.value,
                "remote_runtime_transport_available": self.route_ready,
                "execution_route": "remote_runtime" if self.route_ready else "none",
                "next_action": (
                    "use_remote_runtime_transport"
                    if self.route_ready
                    else "keep_remote_runtime_unverified"
                ),
            }
        )
        return payload


def classify_public_streamable_http_failover(
    *,
    endpoint_configured: bool,
    auth_ready: bool,
    protocol_compatible: bool,
    health_payload: Mapping[str, Any] | None,
    readiness_payload: Mapping[str, Any] | None,
    host_connector_capability_available: bool | None,
) -> dict[str, Any]:
    health = health_payload if isinstance(health_payload, Mapping) else {}
    readiness = readiness_payload if isinstance(readiness_payload, Mapping) else {}
    evidence = PublicStreamableHttpEvidence(
        endpoint_configured=bool(endpoint_configured),
        auth_ready=bool(auth_ready),
        protocol_compatible=bool(protocol_compatible),
        gateway_live=(
            health.get("gateway_live") is True
            or str(health.get("status") or "").lower() in {"live", "ok"}
        ),
        runtime_ready=(
            readiness.get("ready") is True
            and str(readiness.get("status") or "ready").lower() in {"ready", "ok"}
        ),
        host_connector_capability_available=host_connector_capability_available is True,
    )
    payload = evidence.to_dict()
    if not evidence.endpoint_configured:
        reason = "public_mcp_endpoint_not_configured"
    elif not evidence.auth_ready:
        reason = "public_mcp_auth_not_verified"
    elif not evidence.protocol_compatible:
        reason = "public_mcp_protocol_not_verified"
    elif not evidence.gateway_live:
        reason = "public_mcp_gateway_not_live"
    elif not evidence.runtime_ready:
        reason = "public_mcp_runtime_not_ready"
    elif not evidence.host_connector_capability_available:
        reason = "chatgpt_connector_capability_not_verified"
    else:
        reason = "public_streamable_http_remote_failover_ready"
    payload["reason_code"] = reason
    payload["truth_boundary"] = (
        "A configured URL or a live HTTP listener is not enough. Public Streamable HTTP "
        "becomes a host-usable Jaźń route only when authentication, MCP 2026-07-28 "
        "compatibility, gateway liveness, runtime readiness and the current host's "
        "connector/app capability are all independently verified."
    )
    return payload


def preferred_verified_remote_transport(
    *,
    public_streamable_http: Mapping[str, Any] | None = None,
    secure_tunnel: Mapping[str, Any] | None = None,
) -> str:
    public_value = (
        public_streamable_http
        if isinstance(public_streamable_http, Mapping)
        else {}
    )
    tunnel_value = secure_tunnel if isinstance(secure_tunnel, Mapping) else {}
    if public_value.get("remote_runtime_transport_available") is True:
        return RemoteTransport.PUBLIC_STREAMABLE_HTTP.value
    if tunnel_value.get("remote_runtime_transport_available") is True:
        return RemoteTransport.OPENAI_SECURE_MCP_TUNNEL.value
    return RemoteTransport.NONE.value


__all__ = [
    "PublicStreamableHttpEvidence",
    "SCHEMA_VERSION",
    "classify_public_streamable_http_failover",
    "preferred_verified_remote_transport",
]
