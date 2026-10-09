from __future__ import annotations

"""Regression gates for fresh, model-visible Jaźń runtime activity evidence."""

from datetime import datetime, timedelta, timezone
from typing import Any, cast

import pytest

from latka_jazn.bridge.secure_host_runtime_gateway import SecureHostRuntimeGateway
from latka_jazn.mcp.tools import jazn_status
from latka_jazn.version import PACKAGE_VERSION_FULL


class _Gateway:
    def __init__(
        self,
        heartbeat: str | None,
        *,
        reachable: bool = True,
        conversation_ready: bool = True,
        runtime_version: str = PACKAGE_VERSION_FULL,
    ) -> None:
        self.heartbeat = heartbeat
        self.reachable = reachable
        self.conversation_ready = conversation_ready
        self.runtime_version = runtime_version

    def status(self) -> dict[str, Any]:
        return {
            "gateway_ok": self.reachable,
            "daemon_reachable": self.reachable,
            "daemon": {
                "daemon_instance_id": "verified-instance-a",
                "runtime_version": self.runtime_version,
                "last_heartbeat_at_utc": self.heartbeat,
                "pid": 4242,
                "runtime_root": "D:/PRIVATE/SHOULD_NOT_LEAK",
            },
            "capability_matrix": {
                "conversation_ready": self.conversation_ready,
            },
        }


def _status(gateway: _Gateway) -> dict[str, Any]:
    result = jazn_status.run(
        cast(SecureHostRuntimeGateway, cast(Any, gateway))
    )
    return cast(dict[str, Any], result["structuredContent"])


def test_fresh_heartbeat_promotes_reachable_matching_runtime() -> None:
    stamp = datetime.now(timezone.utc).isoformat()
    result = _status(_Gateway(stamp))
    assert result["ready"] is True
    assert result["ok"] is True
    assert result["runtime_heartbeat_fresh"] is True
    assert result["runtime_activity"] == {
        "state": "ready",
        "heartbeat_fresh": True,
        "readiness_verified": True,
    }
    assert result["daemon"]["daemon_instance_id"] == "verified-instance-a"
    assert "runtime_root" not in result["daemon"]
    assert "pid" not in result["daemon"]


@pytest.mark.parametrize(
    "heartbeat",
    [
        None,
        "",
        "not-a-timestamp",
        datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
        (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat(),
        (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat(),
    ],
)
def test_stale_missing_or_untrusted_heartbeat_blocks_ready(
    heartbeat: str | None,
) -> None:
    result = _status(_Gateway(heartbeat))
    assert result["gateway_live"] is True
    assert result["daemon_reachable"] is True
    assert result["runtime_heartbeat_fresh"] is False
    assert result["ready"] is False
    assert result["ok"] is False
    assert result["runtime_activity"]["state"] == "stale"
    assert result["runtime_activity"]["readiness_verified"] is False


def test_unreachable_daemon_is_unknown_not_proven_stale() -> None:
    stamp = datetime.now(timezone.utc).isoformat()
    result = _status(_Gateway(stamp, reachable=False))
    assert result["ready"] is False
    assert result["runtime_activity"]["state"] == "unknown"


def test_reachable_matching_heartbeat_with_unready_capability_is_unready() -> None:
    stamp = datetime.now(timezone.utc).isoformat()
    result = _status(_Gateway(stamp, conversation_ready=False))
    assert result["runtime_heartbeat_fresh"] is True
    assert result["ready"] is False
    assert result["runtime_activity"]["state"] == "unready"


def test_runtime_version_mismatch_never_promotes_activity() -> None:
    stamp = datetime.now(timezone.utc).isoformat()
    result = _status(_Gateway(stamp, runtime_version="not-the-package-version"))
    assert result["runtime_heartbeat_fresh"] is True
    assert result["ready"] is False
    assert result["runtime_activity"]["state"] == "unready"
