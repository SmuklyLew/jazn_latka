from __future__ import annotations

"""Evidence-only classifiers for executor-independent MCP runtime routes."""

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Mapping

from latka_jazn.runtime.turn_runtime import RemoteTransport
from latka_jazn.version import PACKAGE_VERSION_FULL, schema_version

SCHEMA_VERSION = schema_version("mcp_remote_runtime")
PUBLIC_CONNECTOR_STATUS_SCHEMA = "jazn_public_mcp_status/v1"
EXPECTED_PUBLIC_MCP_PROTOCOL_VERSION = "2026-07-28"
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


def classify_public_connector_status_failover(
    *,
    status_payload: Mapping[str, Any] | None,
    host_connector_invocation_observed: bool | None,
    expected_runtime_version: str = PACKAGE_VERSION_FULL,
    expected_protocol_version: str = EXPECTED_PUBLIC_MCP_PROTOCOL_VERSION,
    now_utc: datetime | None = None,
    max_evidence_age_seconds: float = DEFAULT_REMOTE_EVIDENCE_MAX_AGE_SECONDS,
) -> dict[str, Any]:
    """Classify a remote route from an actually invoked jazn_status tool.

    This path exists for ChatGPT hosts that can call the installed Jaźń app but
    cannot perform arbitrary HTTP GET probes or create a local process. The
    status payload alone is never enough: the host must separately attest that
    the current surface actually invoked the Jaźń connector action.
    """

    status = status_payload if isinstance(status_payload, Mapping) else {}
    connector_invocation = host_connector_invocation_observed is True
    connector_status_contract_verified = bool(
        status.get("evidence_schema") == PUBLIC_CONNECTOR_STATUS_SCHEMA
        and str(status.get("tool_name") or "") == "jazn_status"
        and str(status.get("public_transport") or "") == "streamable_http"
    )
    protocol_compatible = bool(
        expected_protocol_version
        and str(status.get("protocol_version") or "") == str(expected_protocol_version)
    )
    gateway_live = status.get("gateway_live") is True
    daemon_reachable = status.get("daemon_reachable") is True
    runtime_ready = bool(
        status.get("ok") is True
        and status.get("ready") is True
        and daemon_reachable
    )

    gateway_instance_id = str(status.get("gateway_instance_id") or "").strip()
    gateway_package_version = str(status.get("package_version") or "").strip()
    runtime_instance_id = str(status.get("runtime_instance_id") or "").strip()
    runtime_version = str(status.get("runtime_version") or "").strip()

    gateway_binding_verified = bool(gateway_instance_id)
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
            status.get("observed_at_utc"),
            now_utc=now_utc,
            max_age_seconds=max_evidence_age_seconds,
        )
        and observation_is_fresh(
            status.get("runtime_heartbeat_at_utc")
            or status.get("last_heartbeat_at_utc"),
            now_utc=now_utc,
            max_age_seconds=max_evidence_age_seconds,
        )
    )

    checks = {
        "host_connector_invocation_observed": connector_invocation,
        "connector_status_contract_verified": connector_status_contract_verified,
        "protocol_compatible": protocol_compatible,
        "gateway_live": gateway_live,
        "daemon_reachable": daemon_reachable,
        "runtime_ready": runtime_ready,
        "gateway_binding_verified": gateway_binding_verified,
        "gateway_version_verified": gateway_version_verified,
        "runtime_binding_verified": runtime_binding_verified,
        "runtime_version_verified": runtime_version_verified,
        "evidence_fresh": evidence_fresh,
    }
    blocking_checks = [name for name, ready in checks.items() if ready is not True]
    route_ready = not blocking_checks

    if not connector_invocation:
        reason = "chatgpt_connector_invocation_not_verified"
    elif not connector_status_contract_verified:
        reason = "public_mcp_connector_status_contract_not_verified"
    elif not protocol_compatible:
        reason = "public_mcp_protocol_not_verified"
    elif not gateway_live:
        reason = "public_mcp_gateway_not_live"
    elif not daemon_reachable:
        reason = "public_mcp_daemon_not_reachable"
    elif not runtime_ready:
        reason = "public_mcp_runtime_not_ready"
    elif not gateway_binding_verified:
        reason = "public_mcp_gateway_binding_not_verified"
    elif not gateway_version_verified:
        reason = "public_mcp_gateway_version_mismatch"
    elif not runtime_binding_verified:
        reason = "public_mcp_runtime_binding_not_verified"
    elif not runtime_version_verified:
        reason = "public_mcp_runtime_version_mismatch"
    elif not evidence_fresh:
        reason = "remote_runtime_evidence_stale"
    else:
        reason = "public_streamable_http_connector_probe_ready"

    return {
        "schema_version": SCHEMA_VERSION,
        "package_version": PACKAGE_VERSION_FULL,
        "remote_transport": RemoteTransport.PUBLIC_STREAMABLE_HTTP.value,
        "remote_runtime_transport_available": route_ready,
        "blocking_checks": blocking_checks,
        "execution_route": "remote_runtime" if route_ready else "none",
        "next_action": (
            "use_remote_runtime_transport"
            if route_ready
            else "keep_remote_runtime_unverified"
        ),
        "reason_code": reason,
        "host_connector_invocation_observed": connector_invocation,
        "host_connector_capability_available": connector_invocation,
        "connector_status_contract_verified": connector_status_contract_verified,
        "protocol_compatible": protocol_compatible,
        "gateway_live": gateway_live,
        "daemon_reachable": daemon_reachable,
        "runtime_ready": runtime_ready,
        "gateway_binding_verified": gateway_binding_verified,
        "gateway_version_verified": gateway_version_verified,
        "runtime_binding_verified": runtime_binding_verified,
        "runtime_version_verified": runtime_version_verified,
        "evidence_fresh": evidence_fresh,
        "gateway_instance_id": gateway_instance_id,
        "runtime_instance_id": runtime_instance_id,
        "runtime_version": runtime_version,
        "truth_boundary": (
            "A copied status object, plugin listing, installed flag, URL, or mention is not "
            "connector evidence. This route becomes available only when the current host "
            "actually invokes the Jaźń jazn_status action and that same fresh response binds "
            "the expected MCP protocol, gateway instance/version and persistent daemon "
            "instance/version. Visible Jaźń speech still requires accepted turn finalization."
        ),
    }


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
    "EXPECTED_PUBLIC_MCP_PROTOCOL_VERSION",
    "PUBLIC_CONNECTOR_STATUS_SCHEMA",
    "PublicStreamableHttpEvidence",
    "SCHEMA_VERSION",
    "classify_public_connector_status_failover",
    "classify_public_streamable_http_failover",
    "observation_age_seconds",
    "observation_is_fresh",
    "preferred_verified_remote_transport",
]
