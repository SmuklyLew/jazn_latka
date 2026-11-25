"""Public phase-2 entrypoints share the existing daemon-job authority policy."""
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from latka_jazn.cli_commands import host
from latka_jazn.core import chat_command_contract as bridge, runtime_daemon
from latka_jazn.mcp.tools import jazn_finalize_reply as mcp
from latka_jazn.version import PACKAGE_VERSION_FULL


class _Gateway:
    def note_host_finalization(self, pending: dict[str, Any], *, outcome: str,
                               reason: str, terminal: bool = False) -> dict[str, Any]:
        pytest.fail("denied public ingress must not send a lifecycle mutation")


@pytest.mark.parametrize("case", ["valid", "inactive", "wrong_instance", "wrong_hash", "legacy"])
@pytest.mark.parametrize("channel", ["cli", "mcp"])
def test_public_entrypoints_require_same_live_authority(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case: str, channel: str,
) -> None:
    digest = "a" * 64
    binding = {"turn_id": "turn", "trace_id": "trace", "daemon_request_id": "request",
               "runtime_version": PACKAGE_VERSION_FULL}
    pending = {"found": True, "state": "pending", "binding": binding,
               "request_contract_hash": digest}
    status = {"active_state": "active_trusted", "endpoint_identity_matches": True,
              "endpoint_instance_matches": True, "heartbeat_fresh": True,
              "package_integrity_verified": True, "source_provenance_verified": True,
              "daemon_instance_id": "instance", "runtime_version": PACKAGE_VERSION_FULL,
              "active_root": str(tmp_path)}
    job = {"accepted": True, "request_id": "request", "daemon_instance_id": "instance",
           "awaiting_host_finalization": True, "phase_result_ready": True,
           "host_turn_id": "turn", "host_trace_id": "trace", "host_request_contract_hash": digest}
    if case == "inactive":
        status["active_state"] = "inactive"
    elif case == "wrong_instance":
        job["daemon_instance_id"] = "other"
    elif case == "wrong_hash":
        job["host_request_contract_hash"] = "b" * 64
    elif case == "legacy":
        binding.pop("daemon_request_id")
    monkeypatch.setattr(bridge, "host_request_lifecycle_state", lambda *_a, **_k: pending)
    monkeypatch.setattr(runtime_daemon, "status_daemon", lambda *_a, **_k: status)
    monkeypatch.setattr(runtime_daemon, "chat_daemon_result", lambda *_a, **_k: job)
    monkeypatch.setattr(mcp, "resolve_continuation_token", lambda *_a, **_k: pending)
    calls: list[str] = []

    def transaction(*_a: Any, **_k: Any) -> dict[str, Any]:
        calls.append(channel)
        return {"ok": True, "accepted": True, "host_finalization_lifecycle_complete": True}

    monkeypatch.setattr(host, "finalize_payload", transaction)
    monkeypatch.setattr(mcp, "_finalize_resolved", transaction)
    if channel == "cli":
        result = host.finalize_public_payload(SimpleNamespace(
            root=tmp_path, turn_id="turn", trace_id="trace", host_request_contract_hash=digest,
        ))
    else:
        result = mcp.run_public(root=tmp_path, continuation_token="opaque",
                                final_text="candidate", final_text_sha256=digest,
                                daemon_url="http://127.0.0.1:8787", lifecycle_gateway=_Gateway())
        result = result.get("structuredContent", result)
    assert result["accepted"] is (case == "valid")
    assert calls == ([channel] if case == "valid" else [])
    if case != "valid":
        assert result["action"] == "host_diagnostic"
        assert not result.get("final_visible_text")


def test_cli_lost_finalization_ack_cannot_display_committed_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(host, "authorize_public_host_finalization", lambda *_a, **_k: None)
    monkeypatch.setattr(host, "finalize_payload", lambda _a: {
        "ok": True, "accepted": True, "host_finalization_lifecycle_complete": False,
        "final_visible_text": "already committed",
    })
    result = host.finalize_public_payload(SimpleNamespace(
        root=tmp_path, turn_id="turn", trace_id="trace", host_request_contract_hash="a" * 64,
    ))
    assert result["accepted"] is False
    assert result["recovery_required"] is True
    assert result["must_not_replay"] is True
    assert "final_visible_text" not in result


def test_public_mcp_rejects_non_loopback_daemon_endpoint(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mcp, "resolve_continuation_token", lambda *_a, **_k: pytest.fail("unexpected token resolution"))
    result = mcp.run_public(root=tmp_path, continuation_token="opaque", final_text="candidate",
                            final_text_sha256="a" * 64, daemon_url="http://unapproved.invalid:8787",
                            lifecycle_gateway=_Gateway())
    assert result["structuredContent"]["reason"] == "phase2_daemon_endpoint_invalid"
    assert result["structuredContent"]["accepted"] is False
