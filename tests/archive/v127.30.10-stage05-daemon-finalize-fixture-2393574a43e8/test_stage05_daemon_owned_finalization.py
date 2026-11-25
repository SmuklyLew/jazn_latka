"""Stage 05: daemon-owned public phase-2 authority, settlement and no replay."""
from __future__ import annotations

from pathlib import Path
import threading
from types import SimpleNamespace
from typing import Any

import pytest

from latka_jazn.config import JaznConfig
from latka_jazn.core import chat_command_contract as bridge
from latka_jazn.core import chatgpt_host_pending_store as store
from latka_jazn.core import runtime_daemon as daemon
from latka_jazn.version import PACKAGE_VERSION_FULL


@pytest.mark.parametrize("damage", [
    "none", "shutdown", "wrong_instance", "old_binding", "wrong_request",
    "wrong_trace", "wrong_hash", "claimed", "ack_failed",
])
def test_daemon_serializes_public_phase2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, damage: str,
) -> None:
    server = object.__new__(daemon.JaznDaemonServer)
    server.config = JaznConfig(root=tmp_path)
    server.daemon_instance_id = "instance"
    server.state = daemon.DaemonState(root=str(tmp_path), host="127.0.0.1", port=8787)
    server._chat_jobs_lock = threading.RLock()
    server.shutdown_requested = threading.Event()
    digest = "a" * 64
    job = daemon.DaemonChatJob(
        request_id="r", user_text="synthetic", input_field="message",
        session_id="s", no_carryover=False, client="chatgpt_daemon_bridge",
        status="awaiting_host_finalization", result={"ok": True},
        host_turn_id="t", host_trace_id="x", host_request_contract_hash=digest,
    )
    server.chat_jobs = {"r": job}
    binding = {"daemon_request_id": "r", "daemon_instance_id": "instance",
               "turn_id": "t", "trace_id": "x", "runtime_version": PACKAGE_VERSION_FULL}
    lifecycle: dict[str, Any] = {"found": True, "state": "pending",
                                "binding": binding, "request_contract_hash": digest}
    authority = {"request_id": "r", "daemon_instance_id": "instance",
                 "turn_id": "t", "trace_id": "x", "host_request_contract_hash": digest}
    candidate = {"turn_id": "t", "trace_id": "x", "host_request_contract_hash": digest}
    if damage == "shutdown":
        server.shutdown_requested.set()
    elif damage == "wrong_instance":
        authority["daemon_instance_id"] = "other"
    elif damage == "old_binding":
        binding["daemon_instance_id"] = "old"
    elif damage == "wrong_request":
        binding["daemon_request_id"] = "other"
    elif damage == "wrong_trace":
        candidate["trace_id"] = "other"
    elif damage == "wrong_hash":
        lifecycle["request_contract_hash"] = "b" * 64
    elif damage == "claimed":
        lifecycle["state"] = "claimed"
    calls: list[str] = []

    def persist(**_k: Any) -> tuple[dict[str, Any], list[str]]:
        calls.append("persist")
        # Another thread cannot enter the job/lifecycle transition while the
        # canonical persistence call is running.
        acquired: list[bool] = []
        def competitor() -> None:
            entered = server._chat_jobs_lock.acquire(timeout=0.05)
            acquired.append(entered)
            if entered:
                server._chat_jobs_lock.release()
        worker = threading.Thread(target=competitor)
        worker.start()
        worker.join(2)
        assert acquired == [False]
        return {"ok": True, "final_visible_text": "synthetic"}, []

    def ack(**_k: Any) -> tuple[daemon.DaemonChatJob, dict[str, Any] | None]:
        calls.append("ack")
        if damage == "ack_failed":
            return job, {"ok": False}
        job.status = "completed"
        return job, None

    monkeypatch.setattr(store, "host_request_lifecycle_state", lambda *_a, **_k: lifecycle)
    monkeypatch.setattr(bridge, "persist_chatgpt_host_visible_reply", persist)
    monkeypatch.setattr(bridge, "build_chatgpt_host_presentation_packet", lambda _p: {"action": "display_exact"})
    monkeypatch.setattr(server, "note_public_host_finalization", ack)
    monkeypatch.setattr(store, "mark_daemon_finalization_notification",
                        lambda *_a, **_k: {"state": "consumed", "delivered": True})
    outcome = server.finalize_public_host_candidate(
        authority=authority, candidate=candidate, chat_bridge_meta={}, contract={},
        host_action_evidence=[],
    )["result"]
    if damage == "none":
        assert outcome["accepted"] is True
        assert outcome["host_finalization_lifecycle_complete"] is True
        assert calls == ["persist", "ack"]
        replay = server.finalize_public_host_candidate(
            authority=authority, candidate=candidate, chat_bridge_meta={}, contract={},
            host_action_evidence=[],
        )["result"]
        assert replay["accepted"] is False
        assert calls == ["persist", "ack"]
    else:
        assert outcome["accepted"] is False
        assert "final_visible_text" not in outcome
        assert outcome["must_not_replay"] is True
        assert calls == (["persist", "ack"] if damage == "ack_failed" else [])


def test_public_phase2_lost_post_does_not_fall_back(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def authorize(*_a: Any, **kwargs: Any) -> None:
        kwargs["authority"].update(request_id="r", daemon_instance_id="instance")
        return None

    def lost(*_a: Any, **_k: Any) -> dict[str, Any]:
        calls.append("POST")
        raise TimeoutError("synthetic lost response")

    monkeypatch.setattr(bridge, "authorize_public_host_finalization", authorize)
    monkeypatch.setattr(daemon, "submit_daemon_host_finalization", lost)
    monkeypatch.setattr(bridge, "persist_chatgpt_host_visible_reply",
                        lambda **_k: pytest.fail("local fallback"))
    result, errors = bridge.persist_public_host_visible_reply(
        config=JaznConfig(root=tmp_path), payload={"turn_id": "t", "trace_id": "x"},
        chat_bridge_meta={}, contract={},
    )
    assert not errors
    assert result is not None
    assert result["accepted"] is False
    assert result["request_id"] == "r"
    assert result["recovery_required"] is True
    assert result["must_not_replay"] is True
    assert calls == ["POST"]


def test_instance_is_part_of_phase1_contract_hash() -> None:
    first = {"daemon_request_id": "r", "daemon_instance_id": "first", "turn_id": "t"}
    second = {**first, "daemon_instance_id": "second"}
    assert store.calculate_host_request_contract_hash(first) != store.calculate_host_request_contract_hash(second)
