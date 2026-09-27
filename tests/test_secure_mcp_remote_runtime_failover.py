from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import pytest

from latka_jazn.mcp.secure_tunnel import build_secure_mcp_tunnel_plan, classify_remote_runtime_failover
from latka_jazn.version import PACKAGE_VERSION_FULL

NOW = datetime(2026, 9, 27, 12, 0, 0, tzinfo=timezone.utc)


def _status(now: datetime = NOW, *, ready: bool = True) -> dict[str, object]:
    stamp = now.isoformat()
    return {
        "process_running":True, "healthy":True, "ready":ready,
        "runtime_instance_id":"daemon-tunnel-a",
        "runtime_version":PACKAGE_VERSION_FULL,
        "observed_at_utc":stamp,
        "runtime_heartbeat_at_utc":stamp,
    }


def test_managed_runtime_is_preferred_long_lived_supervision(tmp_path: Path) -> None:
    plan = build_secure_mcp_tunnel_plan(
        tmp_path, tunnel_id="tunnel_test", runtime_alias="jazn-chatgpt",
        tunnel_client_binary="tunnel-client", python_executable="python",
        platform="posix", env={"CONTROL_PLANE_API_KEY":"sk-must-never-be-embedded"},
    ).to_dict()
    assert plan["preferred_supervision"] == "tunnel_client_managed_runtime"
    assert plan["managed_connect_argv"][:5] == ["tunnel-client","runtimes","connect","--alias","jazn-chatgpt"]
    assert "sk-must-never-be-embedded" not in plan["managed_connect_argv"]


def test_remote_failover_requires_tunnel_and_explicit_chatgpt_connector_capability() -> None:
    blocked = classify_remote_runtime_failover(_status(), host_connector_capability_available=None, now_utc=NOW)
    assert blocked["reason_code"] == "chatgpt_connector_capability_not_verified"
    ready = classify_remote_runtime_failover(_status(), host_connector_capability_available=True, now_utc=NOW)
    assert ready["remote_runtime_transport_available"] is True
    assert ready["runtime_binding_verified"] is True
    assert ready["runtime_version_verified"] is True
    assert ready["evidence_fresh"] is True


def test_remote_failover_fails_closed_when_managed_tunnel_is_not_ready() -> None:
    blocked = classify_remote_runtime_failover(_status(ready=False), host_connector_capability_available=True, now_utc=NOW)
    assert blocked["reason_code"] == "secure_mcp_tunnel_not_fully_ready"


def test_remote_failover_rejects_missing_runtime_binding() -> None:
    status = _status()
    status["runtime_instance_id"] = ""
    blocked = classify_remote_runtime_failover(status, host_connector_capability_available=True, now_utc=NOW)
    assert blocked["reason_code"] == "secure_mcp_runtime_binding_not_verified"


def test_remote_failover_rejects_stale_runtime_evidence() -> None:
    blocked = classify_remote_runtime_failover(_status(NOW - timedelta(minutes=10)), host_connector_capability_available=True, now_utc=NOW)
    assert blocked["reason_code"] == "secure_mcp_runtime_evidence_stale"


def test_runtime_alias_must_be_stable_and_whitespace_free(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="runtime_alias_must_be_nonempty_and_whitespace_free"):
        build_secure_mcp_tunnel_plan(tmp_path, runtime_alias="bad alias", env={})
