from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import cast

import pytest

from latka_jazn.bootstrap.chatgpt_host_preflight_parse import (
    executor_observation_from_mapping,
)
from latka_jazn.core.chatgpt_host_executor_contract import (
    HostExecutionRoute,
    aggregate_host_executor_observations,
)
from latka_jazn.mcp.remote_runtime import (
    EXPECTED_PUBLIC_MCP_PROTOCOL_VERSION,
    PUBLIC_CONNECTOR_STATUS_SCHEMA,
    classify_public_connector_status_failover,
)
from latka_jazn.version import PACKAGE_VERSION_FULL


NOW = datetime(2026, 9, 29, 20, 0, 0, tzinfo=timezone.utc)


def _status(now: datetime = NOW) -> dict[str, object]:
    stamp = now.isoformat()
    return {
        "evidence_schema": PUBLIC_CONNECTOR_STATUS_SCHEMA,
        "tool_name": "jazn_status",
        "ok": True,
        "ready": True,
        "gateway_live": True,
        "daemon_reachable": True,
        "protocol_version": EXPECTED_PUBLIC_MCP_PROTOCOL_VERSION,
        "package_version": PACKAGE_VERSION_FULL,
        "public_transport": "streamable_http",
        "gateway_instance_id": "gateway-connector-a",
        "observed_at_utc": stamp,
        "runtime_instance_id": "daemon-connector-a",
        "runtime_version": PACKAGE_VERSION_FULL,
        "runtime_heartbeat_at_utc": stamp,
    }


def test_actual_connector_status_invocation_can_verify_remote_route() -> None:
    result = classify_public_connector_status_failover(
        status_payload=_status(),
        host_connector_invocation_observed=True,
        now_utc=NOW,
    )

    assert result["remote_runtime_transport_available"] is True
    assert result["execution_route"] == "remote_runtime"
    assert result["blocking_checks"] == []
    assert result["reason_code"] == "public_streamable_http_connector_probe_ready"


def test_copied_status_payload_without_observed_connector_call_is_not_capability() -> None:
    result = classify_public_connector_status_failover(
        status_payload=_status(),
        host_connector_invocation_observed=False,
        now_utc=NOW,
    )

    assert result["remote_runtime_transport_available"] is False
    assert result["reason_code"] == "chatgpt_connector_invocation_not_verified"
    assert "host_connector_invocation_observed" in result["blocking_checks"]


def test_connector_probe_rejects_stale_runtime_binding() -> None:
    result = classify_public_connector_status_failover(
        status_payload=_status(NOW - timedelta(minutes=10)),
        host_connector_invocation_observed=True,
        now_utc=NOW,
    )

    assert result["remote_runtime_transport_available"] is False
    assert result["reason_code"] == "remote_runtime_evidence_stale"


def test_connector_probe_rejects_wrong_status_contract() -> None:
    status = _status()
    status["tool_name"] = "some_other_tool"
    result = classify_public_connector_status_failover(
        status_payload=status,
        host_connector_invocation_observed=True,
        now_utc=NOW,
    )

    assert result["remote_runtime_transport_available"] is False
    assert result["reason_code"] == "public_mcp_connector_status_contract_not_verified"


def test_host_preflight_accepts_fresh_status_from_actual_connector_action() -> None:
    status = _status(datetime.now(timezone.utc))
    observation = executor_observation_from_mapping(
        {
            "surface": "ordinary_chat",
            "process_created": False,
            "error_class": "ClientError",
            "remote_runtime_evidence": {
                "transport": "public_streamable_http",
                "connector_status": status,
                "host_connector_invocation_observed": True,
            },
        }
    )

    assert observation.remote_runtime_transport_available is True
    assert observation.remote_runtime_transport == "public_streamable_http"
    assert observation.remote_runtime_reason_code == (
        "public_streamable_http_connector_probe_ready"
    )
    snapshot = aggregate_host_executor_observations([observation])
    assert snapshot.execution_route is HostExecutionRoute.REMOTE_RUNTIME


def test_host_preflight_rejects_mixed_public_probe_modes() -> None:
    status = _status(datetime.now(timezone.utc))
    with pytest.raises(
        ValueError,
        match="remote_runtime_public_evidence_modes_are_mutually_exclusive",
    ):
        executor_observation_from_mapping(
            {
                "surface": "ordinary_chat",
                "process_created": False,
                "remote_runtime_evidence": {
                    "transport": "public_streamable_http",
                    "connector_status": status,
                    "host_connector_invocation_observed": True,
                    "health": cast(dict[str, object], status),
                },
            }
        )
