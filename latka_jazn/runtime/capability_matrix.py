from __future__ import annotations

"""Unified readiness/capability view for Jaźń runtime components.

The matrix intentionally avoids a single monolithic ``fully_ready`` bit.  Each
capability has its own state so MEMORY, transport or external-tool failures can
degrade only the affected feature instead of disabling ordinary dialogue.
"""

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from latka_jazn.memory.availability import build_memory_availability_status
from latka_jazn.memory.living_memory_gateway import LivingMemoryGateway
from latka_jazn.version import schema_version

SCHEMA_VERSION = schema_version("capability_matrix")


@dataclass(frozen=True, slots=True)
class CapabilityState:
    status: str
    available: bool
    required_for_dialogue: bool
    reason: str
    evidence: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _daemon_core_ready(daemon: dict[str, Any]) -> bool:
    if daemon.get("runtime_core_ready") is True:
        return True
    if daemon.get("system_fully_ready") is True:
        return True
    active = str(
        daemon.get("active_state")
        or (daemon.get("runtime_daemon") or {}).get("active_state")
        or ""
    ).strip().lower()
    return active in {"active", "active_trusted", "running", "ready"}


def _daemon_finalization_ready(daemon: dict[str, Any]) -> bool:
    for key in (
        "host_finalization_ready",
        "finalization_ready",
        "activation_truth_gate_eligible",
    ):
        value = daemon.get(key)
        if value is not None:
            return value is True
    return _daemon_core_ready(daemon)


def build_capability_matrix(
    runtime_root: str | Path,
    *,
    gateway_status: dict[str, Any] | None = None,
    mcp_tasks_supported: bool = True,
) -> dict[str, Any]:
    root = Path(runtime_root).expanduser().resolve()
    gateway = dict(gateway_status or {})
    daemon = gateway.get("daemon") if isinstance(gateway.get("daemon"), dict) else {}
    daemon_reachable = gateway.get("daemon_reachable") is True
    auth_configured = gateway.get("daemon_auth_configured") is True
    core_ready = bool(daemon_reachable and _daemon_core_ready(daemon))

    memory = build_memory_availability_status(root)
    recall_evidence: dict[str, Any]
    if not memory.persistent_memory_enabled:
        recall_ready = False
        recall_status = "disabled_by_policy" if memory.mode == "off" else "memory_not_attached"
        recall_evidence = {
            "memory_mode": memory.mode,
            "memory_status": memory.status,
            "memory_search_ready": False,
        }
    else:
        try:
            recall = LivingMemoryGateway(root, discovery_cache_seconds=0).readiness()
        except Exception as exc:  # health aggregation must not crash the runtime
            recall_ready = False
            recall_status = "probe_failed"
            recall_evidence = {
                "memory_mode": memory.mode,
                "memory_status": memory.status,
                "probe_error": f"{type(exc).__name__}:{exc}",
            }
        else:
            recall_ready = bool(recall.get("memory_search_ready"))
            recall_status = str(recall.get("status") or "unknown")
            recall_evidence = {
                "memory_mode": memory.mode,
                "memory_status": memory.status,
                "memory_search_ready": recall_ready,
                "recall_status": recall_status,
                "selected_source_count": int(recall.get("selected_source_count") or 0),
            }

    components = {
        "runtime_core": CapabilityState(
            status="ready" if core_ready else "unavailable",
            available=core_ready,
            required_for_dialogue=True,
            reason=(
                "daemon_reachable_and_core_ready"
                if core_ready
                else "daemon_or_runtime_core_not_ready"
            ),
            evidence={
                "daemon_reachable": daemon_reachable,
                "runtime_core_ready": _daemon_core_ready(daemon),
            },
        ),
        "local_transport": CapabilityState(
            status="ready" if daemon_reachable else "unavailable",
            available=daemon_reachable,
            required_for_dialogue=True,
            reason="authenticated_loopback_gateway" if daemon_reachable else "loopback_gateway_unreachable",
            evidence={
                "gateway_ok": gateway.get("gateway_ok") is True,
                "daemon_auth_configured": auth_configured,
                "transport": gateway.get("transport"),
            },
        ),
        "persistent_memory": CapabilityState(
            status=(
                "ready"
                if memory.persistent_memory_enabled
                else "disabled" if memory.mode == "off" else "optional_absent"
            ),
            available=memory.persistent_memory_enabled,
            required_for_dialogue=memory.persistent_memory_required,
            reason=memory.status,
            evidence=memory.to_dict(),
        ),
        "recall": CapabilityState(
            status="ready" if recall_ready else recall_status,
            available=recall_ready,
            required_for_dialogue=False,
            reason=("verified_memory_source_ready" if recall_ready else recall_status),
            evidence=recall_evidence,
        ),
        "host_finalization": CapabilityState(
            status="ready" if daemon_reachable and _daemon_finalization_ready(daemon) else "degraded",
            available=bool(daemon_reachable and _daemon_finalization_ready(daemon)),
            required_for_dialogue=False,
            reason=(
                "daemon_finalization_ready"
                if daemon_reachable and _daemon_finalization_ready(daemon)
                else "finalization_not_verified"
            ),
            evidence={
                "daemon_reachable": daemon_reachable,
                "finalization_ready": _daemon_finalization_ready(daemon),
            },
        ),
        "mcp_tasks": CapabilityState(
            status="ready" if mcp_tasks_supported else "disabled",
            available=bool(mcp_tasks_supported),
            required_for_dialogue=False,
            reason="io.modelcontextprotocol/tasks" if mcp_tasks_supported else "extension_disabled",
            evidence={"extension": "io.modelcontextprotocol/tasks"},
        ),
        "remote_transport": CapabilityState(
            status="external_unverified",
            available=False,
            required_for_dialogue=False,
            reason="secure_mcp_tunnel_is_external_and_requires_independent_health_evidence",
            evidence={
                "local_package_can_prove_remote_route": False,
                "expected_health_surfaces": ["/healthz", "/readyz", "/health/mcp", "/metrics"],
            },
        ),
    }

    conversation_ready = bool(core_ready and daemon_reachable and memory.core_runtime_allowed)
    degraded = [
        name
        for name, state in components.items()
        if not state.available and not state.required_for_dialogue
    ]
    blockers = [
        name
        for name, state in components.items()
        if not state.available and state.required_for_dialogue
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "conversation_ready": conversation_ready,
        "ordinary_dialogue_allowed": bool(conversation_ready and memory.ordinary_dialogue_allowed),
        "blockers": blockers,
        "degraded_capabilities": degraded,
        "components": {name: state.to_dict() for name, state in components.items()},
        "truth_boundary": (
            "A capability is ready only from current local evidence. Persistent MEMORY and recall are optional in normal "
            "SYSTEM operation. Remote Secure MCP Tunnel readiness cannot be inferred from packaged files or local daemon "
            "readiness and requires independent tunnel health evidence."
        ),
    }


__all__ = ["CapabilityState", "build_capability_matrix"]
