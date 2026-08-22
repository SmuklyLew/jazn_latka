from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest

import main as main_module
from latka_jazn.config import JaznConfig
from latka_jazn.core.chat_command_contract import (
    build_chatgpt_host_bridge_turn_contract,
    build_chatgpt_host_presentation_packet,
)
from latka_jazn.core.chatgpt_host_pending_store import (
    issue_continuation_token,
    persist_pending_host_request,
)
from latka_jazn.core.host_visible_finalization import sha256_host_visible_text
from latka_jazn.mcp.tools import jazn_finalize_reply, jazn_generate_visible_reply


SAMPLE = datetime(2026, 8, 6, 14, 0, tzinfo=timezone.utc)
HEADER = f"🕒 {SAMPLE.astimezone(ZoneInfo('Europe/Warsaw')):%Y-%m-%d %H:%M:%S}"


def _runtime_payload() -> dict[str, Any]:
    payload = {
        "runtime_version": "v15.1.0.3.96-semantic-routing-completion",
        "trace": {"turn_id": "turn-e2e", "trace_id": "trace-e2e", "timestamp_header": HEADER, "timezone": "Europe/Warsaw"},
        "conversation_decision": {
            "detected_user_intent": "post_update_coverage_audit_request",
            "handler_name": "PostUpdateCoverageAuditHandler",
            "route": "post_update_coverage_audit",
            "requires_host_model": True,
            "timestamp_contract": {
                "timezone": "Europe/Warsaw", "sample_iso": SAMPLE.isoformat(),
                "source": "local_fallback", "trusted": False,
            },
        },
        "runtime_turn_contract": {
            "turn_id": "turn-e2e", "trace_id": "trace-e2e",
            "handler_name": "PostUpdateCoverageAuditHandler", "requires_host_model": True,
            "validation": {"accepted": True},
        },
        "final_response_contract": {
            "turn_id": "turn-e2e", "trace_id": "trace-e2e",
            "runtime_version": "v15.1.0.3.96-semantic-routing-completion",
            "requires_host_model": True, "timestamp_header": HEADER,
            "timezone": "Europe/Warsaw", "timestamp_sample_iso": SAMPLE.isoformat(),
            "timestamp_source": "local_fallback", "timestamp_trusted": False,
            "author_id": "latka_runtime", "author_label": "Łatka",
            "author_source": "jazn_runtime", "state_emoticon": "🛠️",
        },
        "runtime_truth_gate": {
            "ok": True, "normal_response_allowed": False,
            "errors": ["model_guided_speech_required"], "degradations": [],
        },
    }
    bridge = build_chatgpt_host_bridge_turn_contract(
        payload,
        user_text="@GitHub czy coś pominięto w patchu?",
        chat_bridge_meta={},
    )
    payload["chatgpt_host_bridge"] = bridge
    return payload


class FakeGateway:
    def __init__(self, root: Path, response: dict[str, Any]) -> None:
        self.root = root
        self.response = response

    def chat(self, message: str, *, session_id: str | None = None) -> dict[str, Any]:
        return self.response

    def issue_continuation(self, response: dict[str, Any]) -> dict[str, Any]:
        bridge = response["chatgpt_host_bridge"]
        persist_pending_host_request(self.root, bridge)
        return issue_continuation_token(
            self.root,
            turn_id=bridge["turn_id"],
            request_contract_hash=bridge["host_request_contract_hash"],
        )


def _patch_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeEngine:
        def __init__(self, config: JaznConfig) -> None:
            self.config = config
        def shutdown(self) -> None:
            pass
        def persist_final_visible_reply(self, **kwargs):
            return {
                "final_visible_text": kwargs["final_text"],
                "turn_id": kwargs["turn_id"],
                "trace_id": kwargs["trace_id"],
            }
    import latka_jazn.core.engine as engine_module
    monkeypatch.setattr(engine_module, "JaznEngine", FakeEngine)


def test_daemon_presentation_and_private_mcp_complete_two_phase_reply(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_engine(monkeypatch)
    runtime = _runtime_payload()
    presented = main_module._prepare_chatgpt_daemon_presentation(
        cfg=JaznConfig(root=tmp_path),
        payload={
            "ok": True, "done": True, "request_id": "request-e2e",
            "job_status": "completed",
            "user_text": "@GitHub czy coś pominięto w patchu?",
            "user_text_sha256": sha256_host_visible_text("@GitHub czy coś pominięto w patchu?"),
            "result": runtime,
        },
        request_id="request-e2e",
    )
    packet = build_chatgpt_host_presentation_packet(presented)
    assert packet["action"] == "generate_then_finalize"
    presented["chatgpt_host_presentation"] = packet

    generated = jazn_generate_visible_reply.run(
        FakeGateway(tmp_path, presented),
        message="@GitHub czy coś pominięto w patchu?",
        session_id="e2e",
    )
    structured = generated["structuredContent"]
    assert structured["action"] == "generate_then_finalize"

    body = "Sprawdziłam siedem punktów aktualizacji i podaję wynik audytu."
    finalized = jazn_finalize_reply.run(
        root=tmp_path,
        continuation_token=structured["continuation_token"],
        final_text=body,
        final_text_sha256=sha256_host_visible_text(body),
    )
    assert finalized["structuredContent"]["action"] == "display_exact"
    assert finalized["structuredContent"]["must_display_exactly"] is True


def test_forbidden_host_voice_gets_one_retry_then_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_engine(monkeypatch)
    runtime = _runtime_payload()
    bridge = runtime["chatgpt_host_bridge"]
    persist_pending_host_request(tmp_path, bridge)
    token = issue_continuation_token(
        tmp_path,
        turn_id=bridge["turn_id"],
        request_contract_hash=bridge["host_request_contract_hash"],
    )["continuation_token"]
    bad = "**Host ChatGPT:** Nie odpowiem jako Łatka."
    first = jazn_finalize_reply.run(
        root=tmp_path,
        continuation_token=token,
        final_text=bad,
        final_text_sha256=sha256_host_visible_text(bad),
    )
    assert first["structuredContent"]["action"] == "generate_then_finalize"
    assert first["structuredContent"]["regeneration_attempt"] == 1
    assert first["isError"] is False

    second = jazn_finalize_reply.run(
        root=tmp_path,
        continuation_token=first["structuredContent"]["continuation_token"],
        final_text=bad,
        final_text_sha256=sha256_host_visible_text(bad),
    )
    assert second["structuredContent"]["action"] == "host_diagnostic"
    assert second["isError"] is True
    assert any("host_regeneration_budget_exhausted" in item for item in second["structuredContent"].get("violations", []))


def test_malformed_runtime_envelope_gets_one_retry_then_body_only_succeeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_engine(monkeypatch)
    runtime = _runtime_payload()
    bridge = runtime["chatgpt_host_bridge"]
    persist_pending_host_request(tmp_path, bridge)
    token = issue_continuation_token(
        tmp_path,
        turn_id=bridge["turn_id"],
        request_contract_hash=bridge["host_request_contract_hash"],
    )["continuation_token"]

    malformed = f"{HEADER}\n🛠️ Host ChatGPT\n\nTreść odpowiedzi."
    first = jazn_finalize_reply.run(
        root=tmp_path,
        continuation_token=token,
        final_text=malformed,
        final_text_sha256=sha256_host_visible_text(malformed),
    )

    assert first["structuredContent"]["action"] == "generate_then_finalize"
    assert first["structuredContent"]["regeneration_attempt"] == 1
    assert first["isError"] is False

    body = "Treść odpowiedzi po bezpiecznej regeneracji."
    second = jazn_finalize_reply.run(
        root=tmp_path,
        continuation_token=first["structuredContent"]["continuation_token"],
        final_text=body,
        final_text_sha256=sha256_host_visible_text(body),
    )

    assert second["structuredContent"]["action"] == "display_exact"
    assert second["isError"] is False
    assert second["structuredContent"]["final_visible_text"].startswith(
        f"{HEADER}\n🛠️ Łatka\n\n"
    )
