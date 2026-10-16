from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from latka_jazn.core.chatgpt_host_pending_store import HostRequestStoreError
from latka_jazn.core import chatgpt_host_pending_store
from latka_jazn.core.runtime_daemon import (
    DAEMON_CHAT_JOB_HOST_PENDING_STATE,
    DaemonChatJob,
    JaznDaemonServer,
)


class _FakeDaemon:
    def __init__(self, root: Path) -> None:
        self.config = SimpleNamespace(root=root)
        self.events: list[tuple[str, str]] = []

    def _terminalize_host_finalization_locked(
        self, _job: DaemonChatJob, *, status: str, reason: str
    ) -> None:
        self.events.append((status, reason))


def _job() -> DaemonChatJob:
    job = DaemonChatJob(
        request_id="request-1",
        user_text="exact input",
        input_field="message",
        session_id="chatgpt-main",
        no_carryover=False,
        client="chatgpt",
    )
    job.status = DAEMON_CHAT_JOB_HOST_PENDING_STATE
    job.host_turn_id = "turn-1"
    job.host_trace_id = "trace-1"
    job.host_request_contract_hash = "a" * 64
    return job


@pytest.mark.parametrize("valid_capture", [True, False])
def test_recovered_consumed_requires_verified_capture(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, valid_capture: bool,
) -> None:
    monkeypatch.setattr(
        chatgpt_host_pending_store, "host_request_lifecycle_state",
        lambda *_args, **_kwargs: {
            "found": True,
            "state": "consumed",
            "request_contract_hash": "a" * 64,
        },
    )

    def capture(*_args: object, **_kwargs: object) -> dict[str, str]:
        if not valid_capture:
            raise HostRequestStoreError("committed_host_request_capture_invalid")
        return {"state": "consumed"}

    monkeypatch.setattr(chatgpt_host_pending_store,
                        "read_committed_host_request", capture)
    daemon = _FakeDaemon(tmp_path)
    reconciled = JaznDaemonServer._reconcile_host_finalization_job_locked(
        daemon, _job()
    )
    assert reconciled is True
    assert daemon.events == (
        [("completed", "host_visible_reply_finalized")]
        if valid_capture
        else [("host_finalization_rejected",
               "committed_host_request_capture_invalid_during_recovery")]
    )


def test_pending_durable_turn_never_marked_completed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        chatgpt_host_pending_store, "host_request_lifecycle_state",
        lambda *_args, **_kwargs: {
            "found": True,
            "state": "pending",
            "request_contract_hash": "a" * 64,
        },
    )
    daemon = _FakeDaemon(tmp_path)
    assert JaznDaemonServer._reconcile_host_finalization_job_locked(
        daemon, _job()
    ) is False
    assert daemon.events == []
