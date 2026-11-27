"""F01: verified HTTP owner gate before cached generation, resume and finalize."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
from typing import Any

import pytest

from latka_jazn.bridge.secure_host_runtime_gateway import GatewayError
from latka_jazn.mcp import server_legacy_v76 as legacy
from latka_jazn.mcp.server import JaznMcpServer
from latka_jazn.mcp.public_turn_owners import PublicTurnOwnerStore
from latka_jazn.config import JaznConfig
from latka_jazn.core import runtime_daemon as daemon
from latka_jazn.core.admission_owner_context import public_owner_digest


def _root(tmp_path: Path) -> Path:
    root = tmp_path / "synthetic-root"
    (root / "local_resources").mkdir(parents=True)
    return root


def _invoke(server: JaznMcpServer, name: str, args: dict[str, Any], subject: str) -> dict[str, Any]:
    return server.call_public_authenticated(
        name, args, owner_subject=subject,
        meta={"authorization": "synthetic-token", "subject": subject},
    )


def test_public_owner_gate_across_restart_and_token_resolution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stage05_public_context: Any,
) -> None:
    root = _root(tmp_path)
    stage05_public_context(root, "alice", None)
    calls: list[str] = []
    polls: list[str] = []

    def dispatch(name: str, args: dict[str, Any], *, request_id: str | None = None) -> dict[str, Any]:
        calls.append(name)
        if name == "jazn_generate_visible_reply":
            runtime = daemon.JaznDaemonServer(
                ("127.0.0.1", 0), daemon.JaznDaemonHandler,
                config=JaznConfig(root=root, memory_mode="off"),
                marker_path=daemon.resolve_active_runtime_marker_path(root),
                hard_worker_process_isolation=False,
            )
            monkeypatch.setattr(runtime, "start_chat_worker", lambda: None)
            monkeypatch.setattr(runtime, "start_chat_watchdog", lambda: None)
            try:
                job, created, error = runtime.submit_chat_job(
                    request_id=request_id, user_text=str(args["message"]),
                    input_field="message", session_id=None, no_carryover=False,
                    client="secure_mcp_gateway", admission_owner_sha256=public_owner_digest("alice"),
                )
                assert job is not None and created and error is None
            finally:
                runtime.close_sessions()
                runtime.server_close()
        return {
            "content": [{"type": "text", "text": "CANARY_RESULT"}],
            "structuredContent": {"ok": True, "action": "display_exact",
                                  "final_visible_text": "CANARY_RESULT"},
            "isError": False,
        }

    def absent(request_id: str) -> dict[str, Any]:
        polls.append(request_id)
        raise GatewayError("daemon_rejected:chat_job_not_found")

    def instance() -> JaznMcpServer:
        server = JaznMcpServer(root=root, token="synthetic-token")
        monkeypatch.setattr(server, "_dispatch", dispatch)
        monkeypatch.setattr(server.gateway, "result", absent)
        return server

    monkeypatch.setattr(legacy, "resolve_continuation_token",
                        lambda *_a: {"binding": {"daemon_request_id": "request-1"}})
    generate = {"request_id": "request-1", "message": "synthetic"}
    resume = {"daemon_request_id": "request-1"}
    finalize = {"continuation_token": "synthetic-token", "final_text": "synthetic",
                "final_text_sha256": "0" * 64}
    assert not _invoke(instance(), "jazn_generate_visible_reply", generate, "alice")["isError"]
    other = instance()
    for name, args in (
        ("jazn_generate_visible_reply", generate),
        ("jazn_generate_visible_reply", {**generate, "idempotency_key": "different"}),
        ("jazn_resume_visible_reply", resume),
        ("jazn_finalize_reply", finalize),
        ("jazn_generate_visible_reply", {**generate, "message": "different"}),
    ):
        result = _invoke(other, name, args, "bob" if args.get("message") != "different" else "alice")
        assert result["isError"] is True
        assert "CANARY_RESULT" not in repr(result)
    assert not _invoke(other, "jazn_generate_visible_reply", generate, "alice")["isError"]
    assert not _invoke(other, "jazn_resume_visible_reply", resume, "alice")["isError"]
    assert not _invoke(other, "jazn_finalize_reply", finalize, "alice")["isError"]
    assert calls == ["jazn_generate_visible_reply", "jazn_resume_visible_reply", "jazn_finalize_reply"]
    assert polls == ["request-1"]

    ledger = daemon.resolve_active_runtime_marker_path(root).parent / "daemon_chat_jobs.json"
    before = ledger.read_bytes()
    damaged = json.loads(before)
    damaged["jobs"][0]["admission_owner_sha256"] = public_owner_digest("bob")
    ledger.write_text(json.dumps(damaged), encoding="utf-8")
    for name, args in (
        ("jazn_generate_visible_reply", generate),
        ("jazn_resume_visible_reply", resume),
        ("jazn_finalize_reply", finalize),
    ):
        result = _invoke(instance(), name, args, "alice")
        assert result["isError"] is True
        assert "CANARY_RESULT" not in repr(result)
    assert calls == ["jazn_generate_visible_reply", "jazn_resume_visible_reply", "jazn_finalize_reply"]
    ledger.write_bytes(before)


@pytest.mark.parametrize("reason", ["daemon_unavailable:TimeoutError", "daemon_rejected:daemon_chat_ledger_unresolved_record", "existing"])
def test_unowned_turn_is_not_adopted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, reason: str,
                                   stage05_public_context: Any) -> None:
    root = _root(tmp_path)
    stage05_public_context(root, "alice", None)
    server = JaznMcpServer(root=root, token="synthetic-token")

    def observe(_request_id: str) -> dict[str, Any]:
        if reason == "existing":
            return {"request_id": "old-request", "done": True}
        raise GatewayError(reason)

    def forbidden(*_args: Any, **_kwargs: Any) -> Any:
        pytest.fail("unowned or uncertain request must not execute")

    monkeypatch.setattr(server.gateway, "result", observe)
    monkeypatch.setattr(server, "_dispatch", forbidden)
    assert _invoke(server, "jazn_generate_visible_reply", {"request_id": "old-request", "message": "synthetic"}, "alice")["isError"]
    assert _invoke(server, "jazn_resume_visible_reply", {"daemon_request_id": "old-request"}, "alice")["isError"]
    assert PublicTurnOwnerStore(root).lookup("old-request") is None


def test_two_owner_reservations_cannot_both_win(tmp_path: Path) -> None:
    root = _root(tmp_path)
    def claim(subject: str) -> bool:
        return PublicTurnOwnerStore(root).reserve("shared", subject, "a" * 64)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(claim, ("alice", "bob")))
    assert results.count(True) == 1
    record = PublicTurnOwnerStore(root).lookup("shared")
    assert record is not None
    assert PublicTurnOwnerStore.matches(record, "alice") == results[0]
    assert PublicTurnOwnerStore.matches(record, "bob") == results[1]
