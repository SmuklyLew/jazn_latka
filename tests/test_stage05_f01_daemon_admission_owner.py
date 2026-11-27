"""F01: the canonical daemon ledger binds the immutable admission owner."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path

import pytest

from latka_jazn.config import JaznConfig
from latka_jazn.core import runtime_daemon as daemon

ALICE = hashlib.sha256(b"synthetic-alice").hexdigest()
BOB = hashlib.sha256(b"synthetic-bob").hexdigest()


def _server(root: Path, monkeypatch: pytest.MonkeyPatch) -> daemon.JaznDaemonServer:
    server = daemon.JaznDaemonServer(
        ("127.0.0.1", 0), daemon.JaznDaemonHandler,
        config=JaznConfig(root=root, memory_mode="off"),
        marker_path=root / "workspace_runtime" / "JAZN_ACTIVE_RUNTIME.json",
        hard_worker_process_isolation=False,
    )
    monkeypatch.setattr(server, "start_chat_worker", lambda: None)
    monkeypatch.setattr(server, "start_chat_watchdog", lambda: None)
    return server


def _submit(server: daemon.JaznDaemonServer, owner: str | None):
    return server.submit_chat_job(
        request_id="synthetic-id", user_text="synthetic private input",
        session_id="synthetic-session", input_field="message",
        no_carryover=False, client="synthetic",
        admission_owner_sha256=owner,
    )


def _close(server: daemon.JaznDaemonServer) -> None:
    server.close_sessions()
    server.server_close()


@pytest.mark.parametrize("owner", [ALICE, None])
def test_owner_is_immutable_across_restart_and_duplicate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, owner: str | None,
) -> None:
    first = _server(tmp_path, monkeypatch)
    try:
        job, created, error = _submit(first, owner)
        assert job is not None and created and error is None
        row = json.loads(first._chat_state_path.read_text(encoding="utf-8"))["jobs"][0]
        assert row["admission_owner_sha256"] == owner
        assert "admission_owner_sha256" not in job.snapshot()
        assert "synthetic private input" not in first._chat_state_path.read_text(encoding="utf-8")
    finally:
        _close(first)
    second = _server(tmp_path, monkeypatch)
    try:
        again, created, error = _submit(second, owner)
        assert again is not None and not created and error is None
        assert again.admission_owner_sha256 == owner
        for other in (ALICE, BOB, None):
            if other == owner:
                continue
            rejected, created, error = _submit(second, other)
            assert rejected is None and not created and error is not None
            assert error["error_code"] == "request_id_conflict"
        assert second._chat_queue.empty()
    finally:
        _close(second)


@pytest.mark.parametrize("other", [BOB, None])
def test_concurrent_different_owner_never_gets_same_job(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, other: str | None,
) -> None:
    server = _server(tmp_path, monkeypatch)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(lambda owner: _submit(server, owner), (ALICE, other)))
        assert sum(created for _, created, _ in outcomes) == 1
        assert sum(job is not None for job, _, _ in outcomes) == 1
        assert sum(error is not None for _, _, error in outcomes) == 1
        assert server._chat_queue.qsize() == 1
    finally:
        _close(server)


@pytest.mark.parametrize("damage", ["delete", "replace"])
def test_witness_detects_owner_loss_or_replacement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, damage: str,
) -> None:
    first = _server(tmp_path, monkeypatch)
    try:
        job, created, error = _submit(first, ALICE)
        assert job is not None and created and error is None
        ledger = first._chat_state_path
        raw = json.loads(ledger.read_text(encoding="utf-8"))
    finally:
        _close(first)
    if damage == "delete":
        raw["jobs"][0].pop("admission_owner_sha256")
    else:
        raw["jobs"][0]["admission_owner_sha256"] = BOB
    ledger.write_text(json.dumps(raw), encoding="utf-8")
    second = _server(tmp_path, monkeypatch)
    try:
        job, created, error = _submit(second, ALICE)
        assert job is None and not created and error is not None
        assert error["error_code"] == "daemon_chat_ledger_unresolved_record"
        assert second._chat_queue.empty()
    finally:
        _close(second)


def test_invalid_owner_refused_before_admission(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    server = _server(tmp_path, monkeypatch)
    try:
        job, created, error = _submit(server, "raw-subject")
        assert job is None and not created and error is not None
        assert error["error_code"] == "invalid_admission_owner"
        assert server._chat_queue.empty()
        assert not server._chat_state_path.exists()
    finally:
        _close(server)
