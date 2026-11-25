"""Stage 05: the public JSONL bridge is transport-only and phase-2 is bound."""
from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

import pytest

from latka_jazn.config import JaznConfig
from latka_jazn.core import chat_command_contract as bridge
from latka_jazn.core import runtime_daemon
from latka_jazn.version import PACKAGE_VERSION_FULL


@pytest.mark.parametrize("command", ["--chat-gpt", "--chat-ollama", "--chat-open-ai"])
@pytest.mark.parametrize("output_mode", ["jsonl", "host_packet", "final_visible_text"])
def test_unbound_jsonl_cannot_create_runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, command: str, output_mode: Any) -> None:
    monkeypatch.setattr(bridge, "DaemonConversationSession", lambda *_a, **_k: pytest.fail("session created"))
    monkeypatch.setattr(bridge, "persist_chatgpt_host_visible_reply", lambda **_k: pytest.fail("finalization attempted"))
    stdout = io.StringIO()
    code = bridge.run_jsonl_chat_bridge(
        config=JaznConfig(root=tmp_path), session_id="test", no_carryover=False,
        command=command, stdin=io.StringIO('{"text":"Hej"}\n'),
        stdout=stdout, output_mode=output_mode,
    )
    assert code == 1
    payload = json.loads(stdout.getvalue())
    assert payload["action"] == "host_diagnostic"
    assert not payload.get("final_visible_text")


def test_jsonl_lost_transport_preserves_preallocated_request_without_replay(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    class Disconnected:
        def __init__(self, *_a: Any, **_k: Any) -> None:
            pass
        def process_user_text(self, _text: str, **kwargs: Any) -> dict[str, Any]:
            calls.append(kwargs["request_id"])
            raise OSError("synthetic disconnect")
        def close(self) -> None:
            pass
    monkeypatch.setattr(bridge, "DaemonConversationSession", Disconnected)
    stdout = io.StringIO()
    assert bridge.run_jsonl_chat_bridge(
        config=JaznConfig(root=tmp_path), session_id="test", no_carryover=False,
        command="--chat-gpt", daemon_bound=True, stdin=io.StringIO('{"text":"Hej"}\n'),
        stdout=stdout,
    ) == 0
    payload = json.loads(stdout.getvalue())
    assert len(calls) == 1 and calls[0]
    assert payload["request_id"] == calls[0]
    assert payload["request_acceptance"] == "unknown"
    assert payload["must_not_replay"] is True
    assert not payload.get("final_visible_text")


@pytest.mark.parametrize("case", ["valid", "inactive", "stale", "wrong_instance", "wrong_job", "wrong_hash", "missing_binding"])
def test_jsonl_phase2_requires_live_bound_job(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case: str) -> None:
    digest = "a" * 64
    payload = {
        "type": "host_visible_reply", "turn_id": "turn", "trace_id": "trace",
        "final_text": "test", "timestamp_header": "test", "timezone": "UTC",
        "timestamp_sample_iso": "test", "timestamp_source": "test",
        "timestamp_trusted": True, "author_id": "test", "author_label": "test",
        "author_source": "jazn_runtime", "state_emoticon": "test",
        "final_text_sha256": digest, "host_request_contract_hash": digest,
    }
    binding = {"turn_id": "turn", "trace_id": "trace", "daemon_request_id": "request",
               "runtime_version": PACKAGE_VERSION_FULL}
    record = {"found": True, "state": "pending", "binding": binding, "request_contract_hash": digest}
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
    elif case == "stale":
        status["heartbeat_fresh"] = False
    elif case == "wrong_instance":
        job["daemon_instance_id"] = "other"
    elif case == "wrong_job":
        job["request_id"] = "other"
    elif case == "wrong_hash":
        job["host_request_contract_hash"] = "b" * 64
    elif case == "missing_binding":
        binding.pop("daemon_request_id")
    monkeypatch.setattr(bridge, "host_request_lifecycle_state", lambda *_a, **_k: record)
    monkeypatch.setattr(runtime_daemon, "status_daemon", lambda *_a, **_k: status)
    monkeypatch.setattr(runtime_daemon, "chat_daemon_result", lambda *_a, **_k: job)
    reason = bridge._jsonl_phase2_authorization_error(JaznConfig(root=tmp_path), payload,
                                                     host="127.0.0.1", port=8787, marker_output=None)
    if case == "valid":
        assert reason is None
    else:
        assert reason is not None
        monkeypatch.setattr(bridge, "persist_chatgpt_host_visible_reply", lambda **_k: pytest.fail("unauthorized finalization"))
        stdout = io.StringIO()
        assert bridge.run_jsonl_chat_bridge(
            config=JaznConfig(root=tmp_path), session_id="test", no_carryover=False,
            command="--chat-gpt", daemon_bound=True, stdin=io.StringIO(json.dumps(payload) + "\n"),
            stdout=stdout,
        ) == 0
        result = json.loads(stdout.getvalue())
        assert result["ok"] is False
        assert result["error_code"] == reason
        assert not result.get("final_visible_text")


def test_jsonl_does_not_reconstruct_missing_daemon_phase1(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class MissingContract:
        def __init__(self, *_a: Any, **_k: Any) -> None:
            pass
        def process_user_text(self, _text: str, **kwargs: Any) -> dict[str, Any]:
            return {"ok": True, "daemon_job": {"accepted": True, "request_id": kwargs["request_id"]},
                    "final_visible_text": "unverified"}
        def close(self) -> None:
            pass
    monkeypatch.setattr(bridge, "DaemonConversationSession", MissingContract)
    monkeypatch.setattr(bridge, "persist_pending_host_request", lambda *_a, **_k: pytest.fail("client persisted phase1"))
    stdout = io.StringIO()
    bridge.run_jsonl_chat_bridge(config=JaznConfig(root=tmp_path), session_id="test", no_carryover=False,
                                 command="--chat-gpt", daemon_bound=True, stdin=io.StringIO("Hej\n"), stdout=stdout)
    result = json.loads(stdout.getvalue())
    assert result["ok"] is False
    assert result["error_code"] == "jsonl_daemon_turn_contract_unverified"
    assert not result.get("final_visible_text")
