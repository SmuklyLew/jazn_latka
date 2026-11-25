"""Public CLI and JSONL generation receipts share the owning-daemon authority gate."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

import main as main_module
from latka_jazn.config import JaznConfig
from latka_jazn.core import chat_command_contract as contract


@pytest.mark.parametrize("wrapper", ["raw_job", "unwrapped"])
@pytest.mark.parametrize("damage", ["none", "stale_instance", "wrong_job", "missing_contract", "wrong_hash", "not_pending", "authority_denied"])
def test_public_phase1_requires_exact_job_and_live_authority(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, wrapper: str, damage: str,
) -> None:
    bridge: dict[str, Any] = {"phase": "host_visible_generation_requested", "pending_request_persisted": True,
            "host_must_generate_visible_reply": True, "daemon_request_id": "r", "daemon_instance_id": "i",
            "turn_id": "t", "trace_id": "x", "host_request_contract_hash": "a" * 64,
            "host_generation_context": {"synthetic": "private-context"}}
    job: dict[str, Any] = {"accepted": True, "request_id": "r", "daemon_instance_id": "i",
        "phase_result_ready": True, "awaiting_host_finalization": True,
        "host_turn_id": "t", "host_trace_id": "x", "host_request_contract_hash": "a" * 64}
    candidate = {"chatgpt_host_bridge": bridge}
    if damage == "stale_instance":
        job["daemon_instance_id"] = "other"
    elif damage == "wrong_job":
        job["request_id"] = "other"
    elif damage == "missing_contract":
        candidate.clear()
    elif damage == "wrong_hash":
        job["host_request_contract_hash"] = "b" * 64
    elif damage == "not_pending":
        job["phase_result_ready"] = False

    def authorize(*_a: Any, **kwargs: Any) -> str | None:
        if damage == "authority_denied":
            return "phase2_daemon_not_verified"
        kwargs["authority"].update(request_id="r", daemon_instance_id="i")
        return None

    monkeypatch.setattr(contract, "authorize_public_host_finalization", authorize)
    payload = {**job, "result": candidate} if wrapper == "raw_job" else {**candidate, "daemon_job": job}
    reason = contract.public_phase1_authorization_error(JaznConfig(root=tmp_path), payload,
        request_id="r", host="127.0.0.1", port=8787)
    if damage == "none":
        assert reason is None
    else:
        assert reason
        diagnostic = contract.public_phase1_diagnostic("r", reason)
        assert diagnostic["action"] == "host_diagnostic"
        assert diagnostic["must_not_replay"] is True
        assert "private-context" not in str(diagnostic)
        assert "host_generation_context" not in diagnostic


def test_public_cli_presentation_never_reconstructs_missing_phase1(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main_module, "attach_chatgpt_host_contract", lambda *_a, **_k: pytest.fail("client finalization contract write"))
    monkeypatch.setattr(main_module, "_resolve_daemon_user_text_binding", lambda **_k: ("synthetic", None))
    result = main_module._prepare_chatgpt_daemon_presentation(cfg=JaznConfig(root=tmp_path),
        payload={"done": True, "request_id": "r", "result": {"final_visible_text": "unverified"}},
        request_id="r", public_transport=True)
    assert result["action"] == "host_diagnostic"
    assert result["must_not_replay"] is True
    assert not result.get("final_visible_text")
