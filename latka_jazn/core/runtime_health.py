from __future__ import annotations

"""Evidence-based health classification for persistent Jaźń daemons."""

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Mapping

from latka_jazn.version import PACKAGE_VERSION_FULL, schema_version


class DaemonHealthClass(str, Enum):
    HEALTHY = "healthy"
    TRANSIENT = "transient"
    RECOVER = "recover"
    IDENTITY_AMBIGUOUS = "identity_ambiguous"


IDENTITY_BLOCKING_REASONS = frozenset(
    {
        "package_integrity_verification_failed",
        "source_provenance_not_verified",
        "active_runtime_marker_missing",
        "active_root_marker_invalid",
        "endpoint_runtime_root_mismatch",
        "endpoint_daemon_instance_mismatch",
        "endpoint_pid_mismatch",
        "pid_reused_process_fingerprint_mismatch",
    }
)

RECOVERABLE_REASONS = frozenset(
    {
        "daemon_process_not_confirmed",
        "endpoint_identity_confirmed_heartbeat_stale",
        "fresh_marker_and_live_pid_endpoint_unreachable",
        "live_pid_but_heartbeat_stale",
    }
)


@dataclass(frozen=True, slots=True)
class DaemonHealthAssessment:
    classification: DaemonHealthClass
    reason: str
    active_state: str
    active_state_reason: str
    endpoint_reachable: bool | None
    endpoint_identity_matches: bool | None
    heartbeat_is_fresh: bool | None
    process_identity_confirmed: bool | None
    process_fingerprint_match: bool | None
    schema_version: str = schema_version("daemon_health_assessment")
    package_version: str = PACKAGE_VERSION_FULL

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["classification"] = self.classification.value
        return payload


def _optional_bool(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def classify_daemon_health(status: Mapping[str, Any] | None) -> DaemonHealthAssessment:
    value: Mapping[str, Any] = status if isinstance(status, Mapping) else {}
    active_state = str(value.get("active_state") or value.get("runtime_active_state") or "inactive")
    reason = str(value.get("active_state_reason") or "status_reason_missing")
    endpoint_reachable = _optional_bool(value.get("endpoint_reachable"))
    endpoint_identity_matches = _optional_bool(value.get("endpoint_identity_matches"))
    heartbeat_is_fresh = _optional_bool(value.get("heartbeat_is_fresh"))
    process_identity_confirmed = _optional_bool(value.get("process_identity_confirmed"))
    process_fingerprint_match = _optional_bool(value.get("process_fingerprint_match"))

    identity_ambiguous = bool(
        reason in IDENTITY_BLOCKING_REASONS
        or endpoint_identity_matches is False
        or process_fingerprint_match is False
        or value.get("identity_state") in {"identity_mismatch", "process_fingerprint_mismatch"}
    )
    if identity_ambiguous:
        classification = DaemonHealthClass.IDENTITY_AMBIGUOUS
    elif active_state == "active_trusted":
        classification = DaemonHealthClass.HEALTHY
    elif active_state == "active_degraded" and reason in RECOVERABLE_REASONS:
        classification = DaemonHealthClass.RECOVER
    elif active_state == "inactive" and reason in RECOVERABLE_REASONS:
        classification = DaemonHealthClass.RECOVER
    elif active_state == "inactive" and value.get("pid_alive") is False:
        classification = DaemonHealthClass.RECOVER
    elif active_state in {"active_degraded", "active_unverified"}:
        classification = DaemonHealthClass.TRANSIENT
    else:
        classification = DaemonHealthClass.TRANSIENT

    return DaemonHealthAssessment(
        classification=classification,
        reason=reason,
        active_state=active_state,
        active_state_reason=reason,
        endpoint_reachable=endpoint_reachable,
        endpoint_identity_matches=endpoint_identity_matches,
        heartbeat_is_fresh=heartbeat_is_fresh,
        process_identity_confirmed=process_identity_confirmed,
        process_fingerprint_match=process_fingerprint_match,
    )
