from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from latka_jazn.bridge.secure_host_runtime_gateway import SecureHostRuntimeGateway
from latka_jazn.mcp.chatgpt_toolset import REQUIRED_CHATGPT_TURN_TOOLS
from latka_jazn.version import PACKAGE_VERSION_FULL


def _component_projection(value: object) -> dict[str, Any]:
    item = dict(value) if isinstance(value, Mapping) else {}
    return {
        "status": item.get("status"),
        "available": item.get("available") is True,
        "required_for_dialogue": item.get("required_for_dialogue") is True,
        "reason": item.get("reason"),
    }


def _redacted_capability_matrix(value: object) -> dict[str, Any]:
    capability = dict(value) if isinstance(value, Mapping) else {}
    components_value = capability.get("components")
    components = (
        dict(components_value) if isinstance(components_value, Mapping) else {}
    )
    return {
        "conversation_ready": capability.get("conversation_ready") is True,
        "ordinary_dialogue_allowed": (
            capability.get("ordinary_dialogue_allowed") is True
        ),
        "continuity_ready": capability.get("continuity_ready") is True,
        "full_autobiographical_recall_ready": (
            capability.get("full_autobiographical_recall_ready") is True
        ),
        "components": {
            "persistent_memory": _component_projection(
                components.get("persistent_memory")
            ),
            "recall": _component_projection(components.get("recall")),
        },
    }


def _redacted_daemon_binding(value: object) -> dict[str, Any]:
    daemon = dict(value) if isinstance(value, Mapping) else {}
    return {
        "endpoint_reachable": daemon.get("endpoint_reachable") is True,
        "daemon_instance_id": (
            str(daemon.get("daemon_instance_id") or "").strip() or None
        ),
        "runtime_version": str(daemon.get("runtime_version") or "").strip() or None,
        "last_heartbeat_at_utc": (
            str(daemon.get("last_heartbeat_at_utc") or "").strip() or None
        ),
    }


def run(gateway: SecureHostRuntimeGateway) -> dict[str, Any]:
    private_status = dict(gateway.status())
    capability = _redacted_capability_matrix(
        private_status.get("capability_matrix")
    )
    daemon = _redacted_daemon_binding(private_status.get("daemon"))

    gateway_live = private_status.get("gateway_ok") is True
    daemon_reachable = private_status.get("daemon_reachable") is True
    runtime_instance_id = str(daemon.get("daemon_instance_id") or "").strip()
    runtime_version = str(daemon.get("runtime_version") or "").strip()
    ready = bool(
        gateway_live
        and daemon_reachable
        and capability.get("conversation_ready") is True
        and runtime_instance_id
        and runtime_version == PACKAGE_VERSION_FULL
    )
    observed_at_utc = datetime.now(timezone.utc).isoformat()

    status = {
        "tool_name": "jazn_status",
        "ok": ready,
        "ready": ready,
        "gateway_live": gateway_live,
        "daemon_reachable": daemon_reachable,
        "package_version": PACKAGE_VERSION_FULL,
        "observed_at_utc": observed_at_utc,
        "runtime_instance_id": runtime_instance_id or None,
        "runtime_version": runtime_version or None,
        "runtime_heartbeat_at_utc": daemon.get("last_heartbeat_at_utc"),
        "daemon": daemon,
        "capability_matrix": capability,
        "required_chatgpt_turn_tools": list(REQUIRED_CHATGPT_TURN_TOOLS),
        "fresh_conversation_reverification_required": True,
        "current_message_toolset_observation_required": True,
        "catalog_or_installed_state_sufficient": False,
    }
    text = (
        "Jaźń runtime gateway is ready."
        if ready
        else "Jaźń runtime gateway is not conversation-ready."
    )
    return {
        "content": [{"type": "text", "text": text}],
        "structuredContent": status,
        "_meta": {
            "tool": "jazn_status",
            "redacted_model_visible_status": True,
        },
        "isError": not gateway_live,
    }
