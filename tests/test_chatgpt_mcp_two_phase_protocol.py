from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from typing import Any

import pytest

from latka_jazn.bridge import secure_host_runtime_gateway as gateway_module
from latka_jazn.bridge.secure_host_runtime_gateway import GatewayConfig, SecureHostRuntimeGateway
from latka_jazn.cli_commands.diagnostics import _daemon_runtime_write_ready
from latka_jazn.core.chatgpt_host_pending_store import (
    HostRequestStoreError,
    calculate_host_request_contract_hash,
    calculate_runtime_context_sha256,
    claim_pending_host_request,
    cleanup_expired_host_requests,
    consume_claimed_host_request,
    issue_continuation_token,
    persist_pending_host_request,
    resolve_continuation_token,
)
from latka_jazn.core.host_visible_finalization import sha256_host_visible_text
from latka_jazn.core.full_canon_model_context import build_full_canon_model_context
from latka_jazn.core.host_model_bridge import build_host_model_context
from latka_jazn.core.runtime_session import _host_finalization_pending
from latka_jazn.mcp.server import TOOL_DEFINITIONS
from latka_jazn.mcp.tools import jazn_finalize_reply, jazn_generate_visible_reply


def _bridge(turn_id: str = "turn-1") -> dict[str, Any]:
    host_model_context = build_host_model_context(
        {
            "schema_version": "model_context_packet/test",
            "user_text": "Opowiedz coś naturalnie.",
            "nlg_plan": {
                "answer_kind": "natural_dialogue",
                "memory_policy": "not_needed",
                "source_policy": "runtime_only",
            },
            "operational_thought_frame": {"selected_goal": "odpowiedzieć naturalnie"},
            "voice_source_contract": {"identity_name": "Łatka", "grammar_gender": "feminine"},
            "full_canon_model_context": build_full_canon_model_context(),
            "allowed_memory_items": [],
            "forbidden_claims": ["invented_memory_or_unbacked_recall"],
            "required_truth_boundaries": ["Nie udawaj biologicznego życia."],
            "output_instructions": ["Odpowiedz po polsku."],
        },
        detected_intent="ordinary_conversation",
        route="ordinary_dialogue",
    )
    value: dict[str, Any] = {
        "runtime_version": "test-runtime",
        "phase": "host_visible_generation_requested",
        "turn_id": turn_id,
        "trace_id": f"trace-{turn_id}",
        "timestamp_header": "🕒 2026-08-02 00:30:00",
        "timezone": "Europe/Warsaw",
        "timestamp_sample_iso": "2026-08-02T00:30:00+02:00",
        "timestamp_source": "test",
        "timestamp_trusted": True,
        "author_id": "latka",
        "author_label": "Łatka",
        "author_source": "runtime_canon",
        "state_emoticon": "🌿",
        "user_text_sha256": "a" * 64,
        "finalization_contract_hash": "b" * 64,
        "runtime_summary": {"requires_host_model": True},
        "runtime_ownership_contract": {"runtime_owns_identity": True},
        "host_generation_policy": {"rules": ["Use only runtime context"]},
        "host_model_context": host_model_context,
    }
    value["runtime_context_sha256"] = calculate_runtime_context_sha256(value)
    value["host_request_contract_hash"] = calculate_host_request_contract_hash(value)
    return value


def test_continuation_token_is_opaque_expiring_and_one_shot(tmp_path: Path) -> None:
    bridge = _bridge()
    record = persist_pending_host_request(tmp_path, bridge, ttl_seconds=30)
    first = issue_continuation_token(
        tmp_path,
        turn_id=bridge["turn_id"],
        request_contract_hash=bridge["host_request_contract_hash"],
    )
    second = issue_continuation_token(
        tmp_path,
        turn_id=bridge["turn_id"],
        request_contract_hash=bridge["host_request_contract_hash"],
    )
    assert first["continuation_token"] == second["continuation_token"]
    assert first["continuation_token"].startswith("jct1.")
    assert first["continuation_token"] not in json.dumps(record, ensure_ascii=False)

    resolved = resolve_continuation_token(tmp_path, first["continuation_token"])
    assert resolved["state"] == "pending"
    claimed = claim_pending_host_request(
        tmp_path,
        turn_id=bridge["turn_id"],
        request_contract_hash=bridge["host_request_contract_hash"],
    )
    assert claimed["state"] == "claimed"
    consumed = consume_claimed_host_request(
        tmp_path,
        turn_id=bridge["turn_id"],
        request_contract_hash=bridge["host_request_contract_hash"],
    )
    assert consumed["state"] == "consumed"
    with pytest.raises(HostRequestStoreError, match="host_request_replay_detected"):
        resolve_continuation_token(tmp_path, first["continuation_token"])


def test_expired_continuation_is_quarantined(tmp_path: Path) -> None:
    bridge = _bridge("turn-expired")
    persist_pending_host_request(tmp_path, bridge, ttl_seconds=30)
    issued = issue_continuation_token(
        tmp_path,
        turn_id=bridge["turn_id"],
        request_contract_hash=bridge["host_request_contract_hash"],
    )
    cleanup = cleanup_expired_host_requests(
        tmp_path,
        now=datetime.now(timezone.utc) + timedelta(minutes=2),
    )
    assert cleanup["pending_expired"] == 1
    with pytest.raises(HostRequestStoreError, match="host_request_expired"):
        resolve_continuation_token(tmp_path, issued["continuation_token"])


def test_gateway_sends_private_daemon_capability_token(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token_path = tmp_path / "workspace_runtime" / "daemon" / "capability.token"
    token_path.parent.mkdir(parents=True)
    token_path.write_text("daemon-secret\n", encoding="utf-8")
    captured: dict[str, Any] = {}

    class _Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, _limit: int) -> bytes:
            return b'{"ok":true}'

    def _urlopen(request, timeout: float):
        captured["headers"] = {key.lower(): value for key, value in request.header_items()}
        captured["timeout"] = timeout
        return _Response()

    monkeypatch.setattr(gateway_module.request, "urlopen", _urlopen)
    gateway = SecureHostRuntimeGateway(
        GatewayConfig(runtime_root=tmp_path, daemon_url="http://127.0.0.1:8787")
    )
    assert gateway._http_json("GET", "/status") == {"ok": True}
    assert captured["headers"]["x-jazn-daemon-token"] == "daemon-secret"


def test_generation_tool_returns_intermediate_action_not_visible_reply() -> None:
    class _Gateway:
        def chat(self, _message: str, *, session_id: str | None = None) -> dict[str, Any]:
            assert session_id == "session-1"
            return {
                "action": "generate_then_finalize",
                "type": "chatgpt_host_presentation",
                "turn_id": "turn-1",
                "trace_id": "trace-1",
                "required_visible_prefix": "🕒 test",
                "chatgpt_host_bridge": {
                    "host_generation_policy": {"rules": ["Use only runtime context"]},
                    "host_generation_rules": ["Do not display before finalization"],
                    "host_model_context": {"context_sha256": "e" * 64, "model_context": {"user_text": "dokładna wiadomość"}},
                    "host_request_contract_hash": "d" * 64,
                    "turn_id": "turn-1",
                },
            }

        def issue_continuation(self, _response: dict[str, Any]) -> dict[str, Any]:
            return {
                "continuation_token": "jct1.token",
                "expires_at_utc": "2026-08-02T00:45:00+00:00",
                "turn_id": "turn-1",
                "trace_id": "trace-1",
                "request_contract_hash": "d" * 64,
            }

    result = jazn_generate_visible_reply.run(
        _Gateway(),  # type: ignore[arg-type]
        message="dokładna wiadomość",
        session_id="session-1",
    )
    structured = result["structuredContent"]
    assert result["isError"] is False
    assert structured["action"] == "generate_then_finalize"
    assert structured["continuation_token"] == "jct1.token"
    assert structured["must_not_display_intermediate"] is True
    assert structured["host_model_context"]["model_context"]["user_text"] == "dokładna wiadomość"
    assert "final_visible_text" not in structured


def test_finalizer_loads_all_immutable_fields_from_pending_store(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bridge = _bridge()
    captured: dict[str, Any] = {}

    monkeypatch.setattr(
        jazn_finalize_reply,
        "resolve_continuation_token",
        lambda _root, _token: {
            "state": "pending",
            "request_contract_hash": bridge["host_request_contract_hash"],
            "binding": bridge,
        },
    )

    final_visible = f'{bridge["timestamp_header"]}\n🌿 Łatka\n\nTreść po akceptacji.'

    def _persist(**kwargs):
        captured.update(kwargs)
        return (
            {
                "final_visible_text": final_visible,
                "chatgpt_host_presentation": {
                    "action": "display_exact",
                    "final_visible_text": final_visible,
                },
                "host_visible_finalization": {"accepted": True},
                "host_request_consumption": {"state": "consumed"},
            },
            [],
        )

    monkeypatch.setattr(jazn_finalize_reply, "persist_chatgpt_host_visible_reply", _persist)
    body = "Treść po akceptacji."
    result = jazn_finalize_reply.run(
        root=tmp_path,
        continuation_token="jct1.opaque-token",
        final_text=body,
        final_text_sha256=sha256_host_visible_text(body),
    )
    assert result["isError"] is False
    payload = captured["payload"]
    assert payload["turn_id"] == bridge["turn_id"]
    assert payload["trace_id"] == bridge["trace_id"]
    assert payload["timestamp_header"] == bridge["timestamp_header"]
    assert payload["author_label"] == "Łatka"
    assert result["structuredContent"]["action"] == "display_exact"


def test_mcp_finalizer_schema_rejects_host_supplied_identity_fields() -> None:
    definition = next(item for item in TOOL_DEFINITIONS if item["name"] == "jazn_finalize_reply")
    schema = definition["inputSchema"]
    properties = schema["properties"]
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == {
        "continuation_token",
        "final_text",
        "final_text_sha256",
    }
    assert "used_memory_item_ids" in properties
    for forbidden in (
        "turn_id",
        "trace_id",
        "timestamp_header",
        "author_id",
        "author_label",
        "state_emoticon",
        "host_request_contract_hash",
    ):
        assert forbidden not in properties
    assert definition["annotations"]["idempotentHint"] is False


def test_status_reads_runtime_write_readiness_from_live_ping() -> None:
    ready, source = _daemon_runtime_write_ready(
        {"runtime_write_ready": None, "ping": {"runtime_write_ready": True}}
    )
    assert ready is True
    assert source == "daemon.ping.runtime_write_ready"


def test_complete_host_contract_is_valid_intermediate_runtime_state() -> None:
    result = {
        "final_visible_text": "",
        "trace": {
            "turn_id": "turn-1",
            "trace_id": "trace-1",
            "timestamp_header": "🕒 2026-08-02 00:30:00",
            "timezone": "Europe/Warsaw",
        },
        "conversation_decision": {
            "requires_host_model": True,
            "state_emoticon": "🌿",
            "timestamp_contract": {
                "sample_iso": "2026-08-02T00:30:00+02:00",
                "source": "test",
                "trusted": True,
                "timezone": "Europe/Warsaw",
            },
        },
        "runtime_turn_contract": {"requires_host_model": True},
        "final_response_contract": {
            "requires_host_model": True,
            "author_id": "latka",
            "author_label": "Łatka",
            "author_source": "runtime_canon",
            "state_emoticon": "🌿",
        },
    }
    pending, missing = _host_finalization_pending(result, can_continue=True)
    assert pending is True
    assert missing == []
