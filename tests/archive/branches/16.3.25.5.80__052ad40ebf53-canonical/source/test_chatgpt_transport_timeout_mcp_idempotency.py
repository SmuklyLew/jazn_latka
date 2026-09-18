from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

import main as main_module  # noqa: F401 - installs canonical runtime overlays
from latka_jazn.bridge.secure_host_runtime_gateway import (
    GatewayConfig,
    GatewayError,
    SecureHostRuntimeGateway,
)
from latka_jazn.config import JaznConfig
from latka_jazn.core import runtime_daemon
from latka_jazn.core.chatgpt_host_pre_response_gate import run_host_pre_response_gate
from latka_jazn.mcp.server import JaznMcpServer
from latka_jazn.mcp.tools import jazn_resume_visible_reply


class TransportTimeoutError(RuntimeError):
    """Host-like transport timeout independent from Python subprocess timeout."""


def _raise_transport_timeout(*_args: object, **_kwargs: object) -> Any:
    raise TransportTimeoutError("response channel timed out after submit")


def test_daemon_submit_transport_timeout_preserves_preallocated_request_id(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(runtime_daemon, "http_json", _raise_transport_timeout)
    monkeypatch.setattr(runtime_daemon, "status_daemon", _raise_transport_timeout)

    payload = runtime_daemon.chat_daemon_submit(
        JaznConfig(root=tmp_path),
        "Spoko. A co pamiętasz?",
        request_id="transport-timeout-request-1",
        session_id="chatgpt-main",
    )

    assert payload["error_code"] == "daemon_chat_submit_failed"
    assert payload["request_id"] == "transport-timeout-request-1"
    assert payload["submit_outcome_authoritative"] is False
    assert payload["safe_recovery"] == "poll_same_request_id_before_any_retry"


def test_secure_mcp_gateway_transport_timeout_becomes_poll_same_request(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gateway = SecureHostRuntimeGateway(
        GatewayConfig(
            runtime_root=tmp_path,
            daemon_url="http://127.0.0.1:8787",
            daemon_token="test-token",
        )
    )

    def fail_http(*_args: object, **_kwargs: object) -> dict[str, Any]:
        raise GatewayError("daemon_unavailable:TransportTimeoutError")

    monkeypatch.setattr(gateway, "_http_json", fail_http)
    result = gateway.chat(
        "Spoko. A co pamiętasz?",
        session_id="chatgpt-main",
        request_id="mcp-request-transport-timeout",
    )

    presentation = result["chatgpt_host_presentation"]
    assert result["request_id"] == "mcp-request-transport-timeout"
    assert result["submit_outcome_authoritative"] is False
    assert presentation["action"] == "poll_runtime"
    assert presentation["daemon_request_id"] == "mcp-request-transport-timeout"
    assert presentation["must_not_resubmit_user_message"] is True
    assert presentation["submit_outcome_authoritative"] is False


def test_secure_mcp_gateway_pending_ack_is_poll_not_new_turn(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: dict[str, Any] = {}
    gateway = SecureHostRuntimeGateway(
        GatewayConfig(
            runtime_root=tmp_path,
            daemon_url="http://127.0.0.1:8787",
            daemon_token="test-token",
        )
    )

    def pending_http(
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        *,
        retry_safe: bool = True,
    ) -> dict[str, Any]:
        observed.update({"method": method, "path": path, "payload": dict(payload or {})})
        return {
            "ok": False,
            "accepted": True,
            "done": False,
            "job_status": "running",
            "request_id": "mcp-request-pending",
        }

    monkeypatch.setattr(gateway, "_http_json", pending_http)
    result = gateway.chat(
        "Dokończ tę samą turę.",
        session_id="chatgpt-main",
        request_id="mcp-request-pending",
    )

    assert observed["payload"]["request_id"] == "mcp-request-pending"
    assert result["chatgpt_host_presentation"]["action"] == "poll_runtime"
    assert result["chatgpt_host_presentation"]["daemon_request_id"] == "mcp-request-pending"


def test_memory_recall_pending_transport_is_not_misclassified_as_missing_recall() -> None:
    runtime_response = {
        "ok": False,
        "accepted": True,
        "done": False,
        "request_id": "memory-pending-1",
        "chatgpt_host_presentation": {
            "type": "chatgpt_host_presentation",
            "action": "poll_runtime",
            "phase": "runtime_result_pending",
            "daemon_request_id": "memory-pending-1",
            "request_id": "memory-pending-1",
            "poll_command": "jazn_resume_visible_reply",
            "must_not_resubmit_user_message": True,
        },
    }

    gate = run_host_pre_response_gate(
        "Spoko. A co pamiętasz?",
        invoke_runtime=lambda _exact: runtime_response,
        requested_runtime_root="/runtime",
    )

    assert gate["ok"] is True
    assert gate["action"] == "poll_runtime"
    assert gate["visible_text"] == ""
    assert gate["runtime_presentation"]["daemon_request_id"] == "memory-pending-1"


def test_resume_transport_timeout_keeps_existing_daemon_request(tmp_path: Path) -> None:
    class Gateway:
        def result(self, request_id: str) -> dict[str, Any]:
            assert request_id == "resume-timeout-1"
            raise GatewayError("daemon_unavailable:TransportTimeoutError")

    result = jazn_resume_visible_reply.run(
        root=tmp_path,
        gateway=Gateway(),
        daemon_request_id="resume-timeout-1",
    )
    structured = result["structuredContent"]

    assert result["isError"] is False
    assert structured["action"] == "poll_runtime"
    assert structured["daemon_request_id"] == "resume-timeout-1"
    assert structured["must_not_resubmit_user_message"] is True
    assert structured["poll_transport_error"] == "daemon_unavailable:TransportTimeoutError"


def test_mcp_jsonrpc_request_identity_is_stable_and_subject_scoped() -> None:
    metadata = {"transport_request_id": "jsonrpc-call-17"}
    first = JaznMcpServer._daemon_request_id(
        "jazn_generate_visible_reply",
        explicit_request_id=None,
        metadata=metadata,
        subject="user-a",
    )
    second = JaznMcpServer._daemon_request_id(
        "jazn_generate_visible_reply",
        explicit_request_id=None,
        metadata=metadata,
        subject="user-a",
    )
    other_subject = JaznMcpServer._daemon_request_id(
        "jazn_generate_visible_reply",
        explicit_request_id=None,
        metadata=metadata,
        subject="user-b",
    )

    assert first == second
    assert first != other_subject
    assert str(first).startswith("mcp-")
    assert len(str(first)) < 128


def test_mcp_dispatch_propagates_request_id_to_gateway(tmp_path: Path) -> None:
    observed: dict[str, Any] = {}

    class Gateway(SecureHostRuntimeGateway):
        def chat(
            self,
            message: str,
            *,
            session_id: str | None = None,
            request_id: str | None = None,
        ) -> dict[str, Any]:
            observed.update(
                {"message": message, "session_id": session_id, "request_id": request_id}
            )
            return {
                "request_id": request_id,
                "chatgpt_host_presentation": {
                    "type": "chatgpt_host_presentation",
                    "action": "poll_runtime",
                    "phase": "runtime_result_pending",
                    "daemon_request_id": request_id,
                    "poll_command": "jazn_resume_visible_reply",
                },
            }

        def issue_continuation(self, response: dict[str, Any]) -> dict[str, Any]:
            raise AssertionError("continuation is not used for poll_runtime")

    server = object.__new__(JaznMcpServer)
    server.root = tmp_path
    server.gateway = Gateway(
        GatewayConfig(
            runtime_root=tmp_path,
            daemon_url="http://127.0.0.1:8787",
            daemon_token="test-token",
        )
    )

    result = server._dispatch(
        "jazn_generate_visible_reply",
        {"message": "Dokładna wiadomość", "session_id": "chatgpt-main"},
        request_id="mcp-propagated-1",
    )

    assert observed == {
        "message": "Dokładna wiadomość",
        "session_id": "chatgpt-main",
        "request_id": "mcp-propagated-1",
    }
    assert result["structuredContent"]["daemon_request_id"] == "mcp-propagated-1"
    assert result["structuredContent"]["must_not_resubmit_user_message"] is True


def test_chatgpt_loader_contract_names_transport_timeout_and_idempotent_resume() -> None:
    root = Path(__file__).resolve().parents[1]
    loader = (root / "docs/runtime/CHATGPT_PROJECT_INSTRUCTIONS.txt").read_text(encoding="utf-8")
    runbook = (root / "AGENTS.chatgpt.md").read_text(encoding="utf-8")

    assert "TransportTimeoutError" in loader
    assert "remote_runtime" in loader
    assert "nie twórz pętli retry" in loader.lower()
    assert "--daemon-request-id" not in loader
    assert "--daemon-request-id" in runbook
    assert "--daemon-result" in runbook
    assert "nie wysyłaj ponownie wiadomości" in runbook
