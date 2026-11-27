"""F01: offline delivery needs the immutable canonical admission identity."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from latka_jazn.config import JaznConfig
from latka_jazn.core import runtime_daemon as daemon
from latka_jazn.core.admission_owner_context import AUTHENTICATED_HTTP_OWNER, public_owner_digest
from latka_jazn.mcp.tools import jazn_resume_visible_reply as resume

ALICE = public_owner_digest("alice")
BOB = public_owner_digest("bob")


def _admit(root: Path, monkeypatch: pytest.MonkeyPatch, owner: str | None = ALICE) -> tuple[Path, Path]:
    server = daemon.JaznDaemonServer(
        ("127.0.0.1", 0), daemon.JaznDaemonHandler,
        config=JaznConfig(root=root, memory_mode="off"),
        marker_path=daemon.resolve_active_runtime_marker_path(root),
        hard_worker_process_isolation=False,
    )
    monkeypatch.setattr(server, "start_chat_worker", lambda: None)
    monkeypatch.setattr(server, "start_chat_watchdog", lambda: None)
    try:
        job, created, error = server.submit_chat_job(
            request_id="synthetic-r", user_text="synthetic input", session_id=None,
            input_field="message", no_carryover=False, client="synthetic",
            admission_owner_sha256=owner,
        )
        assert job is not None and created and error is None
        return server._chat_state_path, server._chat_ledger_guard_path
    finally:
        server.close_sessions()
        server.server_close()


@pytest.mark.parametrize("damage", ["none", "missing_ledger", "missing_witness",
    "changed_owner", "duplicate_id", "ownerless", "foreign", "bad_json"])
def test_offline_owner_proof_is_read_only_and_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, damage: str,
) -> None:
    ledger, guard = _admit(tmp_path, monkeypatch, None if damage == "ownerless" else ALICE)
    if damage == "missing_ledger":
        ledger.unlink()
    elif damage == "missing_witness":
        guard.unlink()
    elif damage in {"changed_owner", "duplicate_id"}:
        data = json.loads(ledger.read_text(encoding="utf-8"))
        if damage == "changed_owner":
            data["jobs"][0]["admission_owner_sha256"] = BOB
        else:
            data["jobs"].append(dict(data["jobs"][0]))
        ledger.write_text(json.dumps(data), encoding="utf-8")
    elif damage == "bad_json":
        ledger.write_text("{", encoding="utf-8")
    before = [(p.exists(), p.read_bytes() if p.exists() else None) for p in (ledger, guard)]
    assert daemon.durable_admission_owner_matches(
        tmp_path, "synthetic-r", BOB if damage == "foreign" else ALICE,
    ) == (damage == "none")
    assert not daemon.durable_admission_owner_matches(tmp_path, "absent", ALICE)
    assert before == [(p.exists(), p.read_bytes() if p.exists() else None) for p in (ledger, guard)]


@pytest.mark.parametrize("subject", ["alice", "bob"])
def test_offline_recovery_never_opens_committed_store_for_other_owner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, subject: str,
) -> None:
    _admit(tmp_path, monkeypatch)
    calls: list[str] = []

    def committed(*_args: Any, **kwargs: Any) -> dict[str, Any]:
        calls.append(str(kwargs["daemon_request_id"]))
        return {"final_visible_text": "synthetic-canary", "action": "display_exact"}

    class Offline:
        def result(self, _request_id: str) -> dict[str, Any]:
            raise resume.GatewayError("daemon_unavailable:synthetic")

    monkeypatch.setattr(resume, "recover_committed_host_presentation", committed)
    token = AUTHENTICATED_HTTP_OWNER.set(subject)
    try:
        result = resume.run_public(
            root=tmp_path, gateway=Offline(), daemon_url="http://127.0.0.1:8787",
            daemon_request_id="synthetic-r", turn_id="t", host_request_contract_hash="a" * 64,
        )
    finally:
        AUTHENTICATED_HTTP_OWNER.reset(token)
    assert calls == (["synthetic-r"] if subject == "alice" else [])
    assert result["isError"] == (subject != "alice")
    assert ("synthetic-canary" in repr(result)) == (subject == "alice")


def test_offline_proof_rejects_witness_changed_during_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, guard = _admit(tmp_path, monkeypatch)
    original = Path.read_bytes
    reads = 0

    def observed(path: Path) -> bytes:
        nonlocal reads
        data = original(path)
        if path == guard:
            reads += 1
            if reads == 2:
                return data + b" "
        return data

    monkeypatch.setattr(Path, "read_bytes", observed)
    assert not daemon.durable_admission_owner_matches(tmp_path, "synthetic-r", ALICE)
    assert reads == 2
