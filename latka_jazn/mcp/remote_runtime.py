from __future__ import annotations

"""Evidence-only classifiers for executor-independent MCP runtime routes."""

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Mapping

from latka_jazn.runtime.turn_runtime import RemoteTransport
from latka_jazn.version import PACKAGE_VERSION_FULL, schema_version

SCHEMA_VERSION = schema_version("mcp_remote_runtime")
DEFAULT_REMOTE_EVIDENCE_MAX_AGE_SECONDS = 120.0
DEFAULT_REMOTE_EVIDENCE_MAX_FUTURE_SKEW_SECONDS = 5.0


def observation_age_seconds(
    value: object,
    *,
    now_utc: datetime | None = None,
) -> float | None:
    """Return signed evidence age in seconds, or None for invalid/unzoned timestamps."""

    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        observed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if observed.tzinfo is None:
        return None
    now = now_utc or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("now_utc_must_be_timezone_aware")
    return (
        now.astimezone(timezone.utc) - observed.astimezone(timezone.utc)
    ).total_seconds()


def observation_is_fresh(
    value: object,
    *,
    now_utc: datetime | None = None,
    max_age_seconds: float = DEFAULT_REMOTE_EVIDENCE_MAX_AGE_SECONDS,
    max_future_skew_seconds: float = DEFAULT_REMOTE_EVIDENCE_MAX_FUTURE_SKEW_SECONDS,
) -> bool:
    age = observation_age_seconds(value, now_utc=now_utc)
    if age is None:
        return False
    return -float(max_future_skew_seconds) <= age <= float(max_age_seconds)


@dataclass(frozen=True, slots=True)
class PublicStreamableHttpEvidence:
    endpoint_configured: bool
    auth_ready: bool
    protocol_compatible: bool
    gateway_live: bool
    runtime_ready: bool
    gateway_binding_verified: bool
    gateway_version_verified: bool
    runtime_binding_verified: bool
    runtime_version_verified: bool
    evidence_fresh: bool
    host_connector_capability_available: bool
    gateway_instance_id: str
    runtime_instance_id: str
    runtime_version: str

    @property
    def blocking_checks(self) -> tuple[str, ...]:
        checks = (
            "endpoint_configured",
            "auth_ready",
            "protocol_compatible",
            "gateway_live",
            "runtime_ready",
            "gateway_binding_verified",
            "gateway_version_verified",
            "runtime_binding_verified",
            "runtime_version_verified",
            "evidence_fresh",
            "host_connector_capability_available",
        )
        return tuple(name for name in checks if getattr(self, name) is not True)

    @property
    def route_ready(self) -> bool:
        return not self.blocking_checks

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.update(
            {
                "schema_version": SCHEMA_VERSION,
                "package_version": PACKAGE_VERSION_FULL,
                "remote_transport": RemoteTransport.PUBLIC_STREAMABLE_HTTP.value,
                "remote_runtime_transport_available": self.route_ready,
                "blocking_checks": list(self.blocking_checks),
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
    expected_runtime_version: str = PACKAGE_VERSION_FULL,
    now_utc: datetime | None = None,
    max_evidence_age_seconds: float = DEFAULT_REMOTE_EVIDENCE_MAX_AGE_SECONDS,
) -> dict[str, Any]:
    health = health_payload if isinstance(health_payload, Mapping) else {}
    readiness = readiness_payload if isinstance(readiness_payload, Mapping) else {}

    health_gateway_instance = str(health.get("gateway_instance_id") or "").strip()
    readiness_gateway_instance = str(readiness.get("gateway_instance_id") or "").strip()
    gateway_package_version = str(health.get("package_version") or "").strip()
    runtime_instance_id = str(
        readiness.get("runtime_instance_id")
        or readiness.get("daemon_instance_id")
        or ""
    ).strip()
    runtime_version = str(readiness.get("runtime_version") or "").strip()

    gateway_binding_verified = bool(
        health_gateway_instance
        and readiness_gateway_instance
        and health_gateway_instance == readiness_gateway_instance
    )
    gateway_version_verified = bool(
        expected_runtime_version
        and gateway_package_version == str(expected_runtime_version)
    )
    runtime_binding_verified = bool(runtime_instance_id)
    runtime_version_verified = bool(
        expected_runtime_version
        and runtime_version == str(expected_runtime_version)
    )
    evidence_fresh = bool(
        observation_is_fresh(
            health.get("observed_at_utc"),
            now_utc=now_utc,
            max_age_seconds=max_evidence_age_seconds,
        )
        and observation_is_fresh(
            readiness.get("observed_at_utc"),
            now_utc=now_utc,
            max_age_seconds=max_evidence_age_seconds,
        )
        and observation_is_fresh(
            readiness.get("runtime_heartbeat_at_utc")
            or readiness.get("last_heartbeat_at_utc"),
            now_utc=now_utc,
            max_age_seconds=max_evidence_age_seconds,
        )
    )

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
        gateway_binding_verified=gateway_binding_verified,
        gateway_version_verified=gateway_version_verified,
        runtime_binding_verified=runtime_binding_verified,
        runtime_version_verified=runtime_version_verified,
        evidence_fresh=evidence_fresh,
        host_connector_capability_available=host_connector_capability_available is True,
        gateway_instance_id=readiness_gateway_instance or health_gateway_instance,
        runtime_instance_id=runtime_instance_id,
        runtime_version=runtime_version,
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
    elif not evidence.gateway_binding_verified:
        reason = "public_mcp_gateway_binding_not_verified"
    elif not evidence.gateway_version_verified:
        reason = "public_mcp_gateway_version_mismatch"
    elif not evidence.runtime_binding_verified:
        reason = "public_mcp_runtime_binding_not_verified"
    elif not evidence.runtime_version_verified:
        reason = "public_mcp_runtime_version_mismatch"
    elif not evidence.evidence_fresh:
        reason = "remote_runtime_evidence_stale"
    elif not evidence.host_connector_capability_available:
        reason = "chatgpt_connector_capability_not_verified"
    else:
        reason = "public_streamable_http_remote_failover_ready"

    payload["reason_code"] = reason
    payload["truth_boundary"] = (
        "A configured URL, live listener, or structurally valid old payload is not enough. "
        "Public Streamable HTTP becomes a host-usable Jaźń route only when authentication, "
        "MCP 2026-07-28 compatibility, gateway liveness, runtime readiness, same-gateway "
        "binding, canonical daemon instance/version binding, fresh observation/heartbeat, "
        "and the current host's connector/app capability are all independently verified."
    )
    return payload


def preferred_verified_remote_transport(
    *,
    public_streamable_http: Mapping[str, Any] | None = None,
    secure_tunnel: Mapping[str, Any] | None = None,
) -> str:
    public_value = public_streamable_http if isinstance(public_streamable_http, Mapping) else {}
    tunnel_value = secure_tunnel if isinstance(secure_tunnel, Mapping) else {}
    if public_value.get("remote_runtime_transport_available") is True:
        return RemoteTransport.PUBLIC_STREAMABLE_HTTP.value
    if tunnel_value.get("remote_runtime_transport_available") is True:
        return RemoteTransport.OPENAI_SECURE_MCP_TUNNEL.value
    return RemoteTransport.NONE.value


__all__ = [
    "DEFAULT_REMOTE_EVIDENCE_MAX_AGE_SECONDS",
    "DEFAULT_REMOTE_EVIDENCE_MAX_FUTURE_SKEW_SECONDS",
    "PublicStreamableHttpEvidence",
    "SCHEMA_VERSION",
    "classify_public_streamable_http_failover",
    "observation_age_seconds",
    "observation_is_fresh",
    "preferred_verified_remote_transport",
]
