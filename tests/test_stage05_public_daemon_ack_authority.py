"""A public daemon ACK requires an intact committed capture, not a claimed outcome."""
from pathlib import Path
import threading
from typing import Any

import pytest

from latka_jazn.config import JaznConfig
from latka_jazn.core import runtime_daemon
from latka_jazn.core import chatgpt_host_pending_store as store


@pytest.mark.parametrize("case", ["valid", "missing", "wrong_request", "wrong_turn", "wrong_trace", "wrong_hash", "unknown_job"])
def test_public_accepted_ack_requires_durable_capture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case: str,
) -> None:
    # The test uses the actual server ingress method and a synthetic job; the
    # existing store validator and job-transition tests remain unchanged.
    server = object.__new__(runtime_daemon.JaznDaemonServer)
    server.config = JaznConfig(root=tmp_path)
    server._chat_jobs_lock = threading.RLock()
    job = runtime_daemon.DaemonChatJob(
        request_id="request", user_text="synthetic", input_field="message",
        session_id="session", no_carryover=False, client="chatgpt_daemon_bridge",
        status="awaiting_host_finalization",
    )
    server.chat_jobs = {} if case == "unknown_job" else {"request": job}
    digest = "a" * 64
    binding = {"daemon_request_id": "request", "turn_id": "turn", "trace_id": "trace"}
    record: dict[str, Any] = {"binding": binding, "request_contract_hash": digest}
    if case == "wrong_request":
        binding["daemon_request_id"] = "other"
    elif case == "wrong_turn":
        binding["turn_id"] = "other"
    elif case == "wrong_trace":
        binding["trace_id"] = "other"
    elif case == "wrong_hash":
        record["request_contract_hash"] = "b" * 64

    def read(*_a: Any, **_k: Any) -> dict[str, Any]:
        if case == "missing":
            raise store.HostRequestStoreError("committed_host_request_missing")
        return record

    calls: list[dict[str, Any]] = []

    def settle(**kwargs: Any) -> tuple[runtime_daemon.DaemonChatJob, None]:
        calls.append(kwargs)
        return job, None

    monkeypatch.setattr(store, "read_committed_host_request", read)
    monkeypatch.setattr(server, "note_host_finalization", settle)
    result, error = server.note_public_host_finalization(
        request_id="request", turn_id="turn", trace_id="trace",
        request_contract_hash=digest, outcome="accepted", reason="synthetic", terminal=True,
    )
    if case == "valid":
        assert error is None and result is job
        assert len(calls) == 1
        assert calls[0]["request_id"] == "request"
    else:
        assert error is not None
        assert error["ok"] is False
        assert not calls
        assert job.status == "awaiting_host_finalization"
        assert job.host_finalization_attempt_count == 0
