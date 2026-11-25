"""Stage 05: public pending phase-1 recovery requires the original live instance."""
from pathlib import Path
from typing import Any

import pytest

from latka_jazn.core import chat_command_contract, chatgpt_host_pending_store as store
from latka_jazn.mcp.tools import jazn_resume_visible_reply as resume
from test_host_finalization_recovery import _bridge, _phase_one_envelope, _FakeRecoveryGateway, REQUEST_ID


@pytest.mark.parametrize("damage", ["none", "old_instance", "missing_instance", "wrong_job", "not_pending", "wrong_hash", "authority_denied"])
def test_public_resume_requires_same_live_instance(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, damage: str) -> None:
    bridge = _bridge()
    bridge["daemon_instance_id"] = "instance"
    bridge["host_request_contract_hash"] = store.calculate_host_request_contract_hash(bridge)
    record = store.persist_pending_host_request(tmp_path, bridge)
    envelope = _phase_one_envelope(bridge)
    envelope.update(accepted=True, daemon_instance_id="instance", awaiting_host_finalization=True,
                    phase_result_ready=True, host_turn_id=bridge["turn_id"], host_trace_id=bridge["trace_id"],
                    host_request_contract_hash=record["request_contract_hash"])
    if damage == "old_instance":
        envelope["daemon_instance_id"] = "other"
    elif damage == "missing_instance":
        envelope.pop("daemon_instance_id")
    elif damage == "wrong_job":
        envelope["request_id"] = "other"
    elif damage == "not_pending":
        envelope["awaiting_host_finalization"] = False
    elif damage == "wrong_hash":
        envelope["host_request_contract_hash"] = "c" * 64

    def authorize(*_a: Any, **kwargs: Any) -> str | None:
        if damage == "authority_denied":
            return "phase2_daemon_not_verified"
        kwargs["authority"].update(request_id=REQUEST_ID, daemon_instance_id="instance")
        return None

    monkeypatch.setattr(chat_command_contract, "authorize_public_host_finalization", authorize)
    gateway = _FakeRecoveryGateway(envelope)
    result = resume.run_public(root=tmp_path, gateway=gateway, daemon_url="http://127.0.0.1:8787",
                               daemon_request_id=REQUEST_ID, host_request_contract_hash=record["request_contract_hash"])
    if damage == "none":
        assert result["isError"] is False
        assert result["structuredContent"]["action"] == "generate_then_finalize"
        assert result["structuredContent"]["continuation_token"]
    else:
        assert result["isError"] is True
        assert result["structuredContent"]["action"] == "host_diagnostic"
        assert "continuation_token" not in result["structuredContent"]
    assert gateway.result_calls == [REQUEST_ID]


def test_public_resume_refuses_external_endpoint_without_poll(tmp_path: Path) -> None:
    gateway = _FakeRecoveryGateway({})
    result = resume.run_public(root=tmp_path, gateway=gateway, daemon_url="http://example.invalid:8787",
                               daemon_request_id=REQUEST_ID)
    assert result["isError"] is True
    assert not gateway.result_calls
