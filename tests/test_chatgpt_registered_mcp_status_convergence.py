from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from typing import Any, cast

from latka_jazn.bootstrap.chatgpt_host_preflight_parse import (
    executor_observation_from_mapping,
)
from latka_jazn.bridge.secure_host_runtime_gateway import SecureHostRuntimeGateway
from latka_jazn.core.chatgpt_host_executor_contract import (
    HostExecutionRoute,
    aggregate_host_executor_observations,
)
from latka_jazn.mcp.chatgpt_toolset import REQUIRED_CHATGPT_TURN_TOOLS
from latka_jazn.mcp.remote_runtime import (
    REGISTERED_MCP_STATUS_SCHEMA,
    classify_registered_mcp_connector_status_failover,
)
from latka_jazn.mcp.server import (
    MCP_PROTOCOL_VERSION_LATEST_LEGACY,
    JaznMcpServer,
)
from latka_jazn.mcp.tools import jazn_status
from latka_jazn.version import PACKAGE_VERSION_FULL


NOW = datetime(2026, 10, 7, 18, 0, 0, tzinfo=timezone.utc)


class _Gateway:
    def __init__(self, *, heartbeat: datetime = NOW) -> None:
        self.heartbeat = heartbeat

    def status(self) -> dict[str, Any]:
        return {
            "gateway_ok": True,
            "daemon_reachable": True,
            "runtime_root": "D:/PRIVATE/JAZN/SHOULD_NOT_LEAK",
            "daemon_auth_configured": True,
            "daemon": {
                "pid": 4242,
                "daemon_instance_id": "daemon-registered-app-a",
                "runtime_version": PACKAGE_VERSION_FULL,
                "last_heartbeat_at_utc": self.heartbeat.isoformat(),
                "active_root": "D:/PRIVATE/JAZN/SHOULD_NOT_LEAK",
                "secret": "never-model-visible",
            },
            "capability_matrix": {
                "conversation_ready": True,
                "ordinary_dialogue_allowed": True,
                "continuity_ready": True,
                "full_autobiographical_recall_ready": False,
                "components": {
                    "persistent_memory": {
                        "status": "ready",
                        "available": True,
                        "required_for_dialogue": False,
                        "reason": "verified",
                        "database_path": "D:/PRIVATE/memory.sqlite3",
                    },
                    "recall": {
                        "status": "ready",
                        "available": True,
                        "required_for_dialogue": False,
                        "reason": "verified",
                        "private_detail": "must-not-leak",
                    },
                },
            },
        }


def _registered_status(*, observed: datetime = NOW) -> dict[str, object]:
    return {
        "evidence_schema": REGISTERED_MCP_STATUS_SCHEMA,
        "tool_name": "jazn_status",
        "ok": True,
        "ready": True,
        "gateway_live": True,
        "daemon_reachable": True,
        "protocol_version": MCP_PROTOCOL_VERSION_LATEST_LEGACY,
        "package_version": PACKAGE_VERSION_FULL,
        "registered_transport": "registered_mcp_app",
        "observed_at_utc": observed.isoformat(),
        "runtime_instance_id": "daemon-registered-app-a",
        "runtime_version": PACKAGE_VERSION_FULL,
        "runtime_heartbeat_at_utc": observed.isoformat(),
    }


def test_model_visible_status_redacts_private_local_operator_details() -> None:
    result = jazn_status.run(cast(SecureHostRuntimeGateway, cast(Any, _Gateway())))
    structured = result["structuredContent"]

    assert structured["ok"] is True
    assert structured["ready"] is True
    assert structured["runtime_instance_id"] == "daemon-registered-app-a"
    assert structured["runtime_version"] == PACKAGE_VERSION_FULL
    assert structured["capability_matrix"]["conversation_ready"] is True
    assert structured["capability_matrix"]["components"]["persistent_memory"][
        "available"
    ] is True

    serialized = json.dumps(result, ensure_ascii=False)
    assert "D:/PRIVATE" not in serialized
    assert "never-model-visible" not in serialized
    assert "database_path" not in serialized
    assert "private_detail" not in serialized
    assert "runtime_root" not in structured
    assert set(structured["daemon"]) == {
        "endpoint_reachable",
        "daemon_instance_id",
        "runtime_version",
        "last_heartbeat_at_utc",
    }


def test_direct_registered_mcp_status_stamp_binds_actual_protocol_without_paths() -> None:
    raw_result = jazn_status.run(cast(SecureHostRuntimeGateway, cast(Any, _Gateway())))
    response = {
        "jsonrpc": "2.0",
        "id": 7,
        "result": raw_result,
    }
    stamped = JaznMcpServer._stamp_registered_mcp_status_response(
        {
            "jsonrpc": "2.0",
            "id": 7,
            "method": "tools/call",
            "params": {"name": "jazn_status", "arguments": {}},
        },
        response,
        protocol_version=MCP_PROTOCOL_VERSION_LATEST_LEGACY,
    )

    assert stamped is not None
    status = stamped["result"]["structuredContent"]
    assert status["evidence_schema"] == REGISTERED_MCP_STATUS_SCHEMA
    assert status["tool_name"] == "jazn_status"
    assert status["registered_transport"] == "registered_mcp_app"
    assert status["protocol_version"] == MCP_PROTOCOL_VERSION_LATEST_LEGACY
    assert status["package_version"] == PACKAGE_VERSION_FULL
    assert "runtime_root" not in status


def test_actual_registered_app_status_invocation_can_verify_remote_route() -> None:
    result = classify_registered_mcp_connector_status_failover(
        status_payload=_registered_status(),
        host_connector_invocation_observed=True,
        callable_tool_names=REQUIRED_CHATGPT_TURN_TOOLS,
        current_message_toolset_observed=True,
        now_utc=NOW,
    )

    assert result["remote_runtime_transport_available"] is True
    assert result["remote_transport"] == "registered_mcp_app"
    assert result["execution_route"] == "remote_runtime"
    assert result["blocking_checks"] == []
    assert result["reason_code"] == "registered_mcp_app_connector_probe_ready"


def test_registered_app_status_requires_actual_current_message_invocation() -> None:
    result = classify_registered_mcp_connector_status_failover(
        status_payload=_registered_status(),
        host_connector_invocation_observed=False,
        callable_tool_names=REQUIRED_CHATGPT_TURN_TOOLS,
        current_message_toolset_observed=True,
        now_utc=NOW,
    )

    assert result["remote_runtime_transport_available"] is False
    assert result["reason_code"] == "chatgpt_connector_invocation_not_verified"
    assert "host_connector_invocation_observed" in result["blocking_checks"]


def test_registered_app_status_rejects_incomplete_current_message_toolset() -> None:
    result = classify_registered_mcp_connector_status_failover(
        status_payload=_registered_status(),
        host_connector_invocation_observed=True,
        callable_tool_names=["jazn_status", "jazn_generate_visible_reply"],
        current_message_toolset_observed=True,
        now_utc=NOW,
    )

    assert result["remote_runtime_transport_available"] is False
    assert result["reason_code"] == "chatgpt_required_turn_toolset_incomplete"
    assert "full_turn_toolset_callable" in result["blocking_checks"]


def test_registered_app_status_rejects_stale_runtime_evidence() -> None:
    stale = NOW - timedelta(minutes=10)
    result = classify_registered_mcp_connector_status_failover(
        status_payload=_registered_status(observed=stale),
        host_connector_invocation_observed=True,
        callable_tool_names=REQUIRED_CHATGPT_TURN_TOOLS,
        current_message_toolset_observed=True,
        now_utc=NOW,
    )

    assert result["remote_runtime_transport_available"] is False
    assert result["reason_code"] == "remote_runtime_evidence_stale"


def test_host_preflight_promotes_verified_registered_app_without_local_executor() -> None:
    observation = executor_observation_from_mapping(
        {
            "surface": "ordinary_chat_registered_app",
            "process_created": False,
            "error_class": "ExecutionUnavailable",
            "remote_runtime_evidence": {
                "transport": "registered_mcp_app",
                "connector_status": _registered_status(
                    observed=datetime.now(timezone.utc)
                ),
                "host_connector_invocation_observed": True,
                "current_message_toolset_observed": True,
                "callable_tool_names": list(REQUIRED_CHATGPT_TURN_TOOLS),
            },
        }
    )

    assert observation.remote_runtime_transport_available is True
    assert observation.remote_runtime_transport == "registered_mcp_app"
    assert observation.remote_runtime_reason_code == (
        "registered_mcp_app_connector_probe_ready"
    )
    snapshot = aggregate_host_executor_observations([observation])
    assert snapshot.execution_route is HostExecutionRoute.REMOTE_RUNTIME
    assert snapshot.remote_runtime_transports == ("registered_mcp_app",)
