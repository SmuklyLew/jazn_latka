"""Stage 04: real loopback HTTP disconnect and independent model-channel scope.

The fixtures use synthetic turns with private MEMORY and model inference off.
A successful loopback contract is not live Cloudflare/MCP acceptance.
"""
from __future__ import annotations

import http.client
import json
from pathlib import Path
from threading import Thread
import time
from types import SimpleNamespace
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from latka_jazn.config import JaznConfig
from latka_jazn.core.conversation_runner import ConversationRunner
from latka_jazn.core.conversation_state_store import ConversationStateStore
from latka_jazn.core.runtime_daemon import (
    DAEMON_AUTH_HEADER,
    JaznDaemonHandler,
    JaznDaemonServer,
)


class _RecordingSession:
    def __init__(self, _config: JaznConfig, *, session_id: str,
                 calls: list[dict[str, Any]], **_kwargs: Any) -> None:
        self.state = SimpleNamespace(session_id=session_id)
        self._calls = calls

    def process_user_text(self, user_text: str, **kwargs: Any) -> dict[str, Any]:
        self._calls.append({
            "session_id": self.state.session_id,
            "user_text": user_text,
            "model_channel": dict(kwargs.get("model_channel_config") or {}),
        })
        return {
            "ok": True, "answer_ok": True,
            "execution_state": "final_visible_answer",
            "session": {"session_id": self.state.session_id},
        }

    def close(self) -> None:
        return None


def test_disconnected_http_client_polls_same_request_and_switches_model(
    tmp_path: Path,
) -> None:
    """Losing an HTTP response must not create a second daemon turn."""
    root = tmp_path / "synthetic_system"
    root.mkdir()
    calls: list[dict[str, Any]] = []
    instances: list[_RecordingSession] = []

    def factory(config: JaznConfig, **kwargs: Any) -> _RecordingSession:
        session = _RecordingSession(config, calls=calls, **kwargs)
        instances.append(session)
        return session

    server = JaznDaemonServer(
        ("127.0.0.1", 0), JaznDaemonHandler,
        config=JaznConfig(root=root, memory_mode="off"),
        marker_path=root / "workspace_runtime" / "JAZN_ACTIVE_RUNTIME.json",
        session_factory=factory,
        hard_worker_process_isolation=False,
        execution_timeout_seconds=30,
    )
    thread = Thread(target=server.serve_forever, kwargs={"poll_interval": 0.02},
                    daemon=True)
    thread.start()
    port = server.server_address[1]
    base_url = f"http://127.0.0.1:{port}"
    headers = {
        "Content-Type": "application/json",
        DAEMON_AUTH_HEADER: server.auth_token,
    }
    first = {
        "message": "synthetic first message",
        "request_id": "stage04-transport-first",
        "session_id": "stage04-transport-session",
        "client": "daemon_http",
        "command": "--chat",
        "model_channel_config": {"model_name": "synthetic-A"},
    }

    def request_json(path: str, payload: dict[str, Any] | None = None
                     ) -> tuple[int, dict[str, Any]]:
        raw = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = Request(base_url + path, data=raw, headers=headers,
                      method="POST" if payload is not None else "GET")
        try:
            with urlopen(req, timeout=5.0) as response:
                return int(response.status), json.load(response)
        except HTTPError as exc:
            return int(exc.code), json.loads(exc.read().decode("utf-8"))

    try:
        # Fully submit the request, then deliberately discard the HTTP reply.
        lost = http.client.HTTPConnection("127.0.0.1", port, timeout=5.0)
        try:
            lost.request("POST", "/chat-submit",
                         body=json.dumps(first).encode("utf-8"), headers=headers)
        finally:
            lost.close()

        observed: dict[str, Any] | None = None
        deadline = time.monotonic() + 12.0
        while time.monotonic() < deadline:
            status, response = request_json(
                "/chat-result/stage04-transport-first"
            )
            if status == 200 and response.get("job_status") == "completed":
                observed = response
                break
            assert status in {200, 202, 404}, response
            time.sleep(0.05)
        assert observed is not None, "submitted request not recovered by HTTP poll"
        assert observed["request_id"] == first["request_id"]
        assert observed["session_id"] == first["session_id"]
        assert observed["result"]["ok"] is True
        assert len(calls) == 1

        status, duplicate = request_json("/chat-submit", first)
        assert status == 200
        assert duplicate["created"] is False
        assert duplicate["idempotent_replay"] is True
        assert len(calls) == 1

        # The channel is part of the request fingerprint, not session identity.
        second = {
            **first,
            "message": "synthetic second message",
            "request_id": "stage04-transport-second",
            "model_channel_config": {"model_name": "synthetic-B"},
        }
        conflict = {**first, "model_channel_config": second["model_channel_config"]}
        status, rejected = request_json("/chat-submit", conflict)
        assert status == 409
        assert rejected["error_code"] == "request_id_conflict"
        assert len(calls) == 1

        status, created = request_json("/chat-submit", second)
        assert status in {200, 202}
        assert created["created"] is True
        deadline = time.monotonic() + 12.0
        while time.monotonic() < deadline:
            status, response = request_json(
                "/chat-result/stage04-transport-second"
            )
            if status == 200 and response.get("job_status") == "completed":
                break
            assert status in {200, 202}, response
            time.sleep(0.05)
        else:
            pytest.fail("second turn did not complete through the same daemon")
        assert len(instances) == 1
        assert [item["session_id"] for item in calls] == [
            first["session_id"], first["session_id"],
        ]
        assert [item["model_channel"] for item in calls] == [
            {"model_name": "synthetic-A"},
            {"model_name": "synthetic-B"},
        ]
        assert server.chat_job_summary()["terminal_failure_total"] == 0
    finally:
        server.shutdown()
        server.close_sessions()
        server.server_close()
        thread.join(timeout=5.0)


def test_turn_scoped_model_change_keeps_real_accepted_session_history(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name, value in {
        "JAZN_RUNTIME_WORKSPACE_DIR": str(tmp_path / "workspace_runtime"),
        "JAZN_MEMORY_ROOT": str(tmp_path / "memory"),
        "JAZN_MEMORY_MODE": "off",
        "JAZN_MODEL_ADAPTER": "null",
        "JAZN_LLM_ROUTE": "off",
        "JAZN_NETWORK_TIME_FIRST": "0",
        "JAZN_NETWORK_TIME_IN_TURN": "0",
        "JAZN_ALLOW_NETWORK": "0",
        "JAZN_DICTIONARY_ALLOW_NETWORK": "0",
        "JAZN_MEMORY_SYNC_MODE": "off",
    }.items():
        monkeypatch.setenv(name, value)
    (tmp_path / "main.py").write_text("# isolated fixture\n", encoding="utf-8")
    runner = ConversationRunner(
        JaznConfig(root=tmp_path, memory_mode="off"),
        session_id="stage04-model-switch",
    )
    try:
        first = runner.process_user_text(
            "Jaka jest godzina?",
            model_channel_config={"model_name": "synthetic-A"},
        )
        assert first["answer_ok"] is True
        assert first["canonical_persistence_ok"] is True
        assert first["session_provenance"]["session_reused"] is False

        second = runner.process_user_text(
            "Zacytuj pierwszych trzech słów mojej poprzedniej wiadomości.",
            model_channel_config={"model_name": "synthetic-B"},
        )
        assert second["answer_ok"] is True
        assert second["canonical_persistence_ok"] is True
        assert second["session_provenance"]["session_reused"] is True
        assert second["conversation_decision"]["body"] == "Jaka jest godzina?"
        assert first["trace"]["turn_id"] != second["trace"]["turn_id"]
        history = ConversationStateStore(tmp_path).load_context_projection(
            "stage04-model-switch"
        )
        assert history["total_turn_count"] == 2
        assert history["invalid_record_count"] == 0
    finally:
        runner.close()
