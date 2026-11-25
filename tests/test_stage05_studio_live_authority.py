"""Stage 05: Studio display must be backed by live daemon and durable turn evidence."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from typing import Any

import pytest

from latka_jazn.core import runtime_daemon
from latka_jazn.core.conversation_state_store import ConversationStateStore
from tools.jazn_run_studio.validation_worker import validate_live


@pytest.mark.parametrize("damage", [
    "none", "inactive", "wrong_instance", "wrong_job", "different_result",
    "missing_record", "wrong_record_hash", "wrong_envelope", "no_instance",
    "external_endpoint", "wrong_root", "wrong_user_hash", "stale_heartbeat",
])
def test_live_studio_final_authority(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, damage: str) -> None:
    body = "Zaakceptowana tura."
    text = "🕒 2026-11-25 16:00:00\n🙂 Łatka\n\n" + body
    user = "Test syntetyczny."
    record = ConversationStateStore(tmp_path).append_finalized_turn(
        session_id="s", turn_id="t", trace_id="x", user_text=user,
        assistant_text=text, source="ollama_jsonl",
    )
    contract = {
        "turn_id": "t", "trace_id": "x", "author_id": "latka_runtime",
        "author_label": "Łatka", "author_source": "jazn_runtime",
        "timestamp_header": "🕒 2026-11-25 16:00:00", "timezone": "UTC",
        "timestamp_sample_iso": "2026-11-25T16:00:00+00:00",
        "timestamp_source": "test", "timestamp_trusted": True,
        "state_emoticon": "🙂", "body": body, "final_visible_text": text,
    }
    result: dict[str, Any] = {
        "ok": True, "answer_ok": True, "execution_state": "final_visible_answer",
        "host_finalization_pending": False, "session": {"session_id": "s"},
        "trace": {"turn_id": "t", "trace_id": "x"}, "final_visible_text": text,
        "final_visible_integrity": {"valid": True, "consensus": True,
                                    "text_sha256": sha256(text.encode()).hexdigest()},
        "runtime_truth_gate": {"ok": True, "normal_response_allowed": True},
        "final_response_contract": contract, "conversation_state_persistence": record,
    }
    live: dict[str, Any] = {
        "ok": True, "accepted": True, "request_id": "r", "session_id": "s",
        "done": True, "job_status": "completed", "completed_at_utc": "test",
        "awaiting_host_finalization": False, "daemon_instance_id": "instance",
        "user_text_sha256": sha256(user.encode()).hexdigest(), "result": result,
    }
    incoming = deepcopy(live)
    status: dict[str, Any] = {
        "active_state": "active_trusted", "endpoint_identity_matches": True,
        "endpoint_instance_matches": True, "heartbeat_fresh": True,
        "package_integrity_verified": True, "source_provenance_verified": True,
        "daemon_instance_id": "instance", "active_root": str(tmp_path),
    }
    endpoint = "http://127.0.0.1:8787"
    if damage == "inactive":
        status["active_state"] = "inactive"
    elif damage == "wrong_instance":
        live["daemon_instance_id"] = "other"
    elif damage == "wrong_job":
        live["request_id"] = "other"
    elif damage == "different_result":
        result["trace"] = {"turn_id": "other", "trace_id": "x"}
    elif damage == "missing_record":
        Path(record["path"]).unlink()
    elif damage == "wrong_record_hash":
        record["record_sha256"] = "a" * 64
    elif damage == "wrong_envelope":
        contract["body"] = "Inna treść."
    elif damage == "no_instance":
        incoming.pop("daemon_instance_id")
    elif damage == "external_endpoint":
        endpoint = "http://example.invalid:8787"
    elif damage == "wrong_root":
        status["active_root"] = str(tmp_path / "other")
    elif damage == "wrong_user_hash":
        live["user_text_sha256"] = "b" * 64
    elif damage == "stale_heartbeat":
        status["heartbeat_fresh"] = False
    monkeypatch.setattr(runtime_daemon, "status_daemon", lambda *_a, **_k: status)
    monkeypatch.setattr(runtime_daemon, "chat_daemon_result", lambda *_a, **_k: live)
    checked = validate_live(incoming, "r", "s", root=tmp_path, daemon_url=endpoint)
    if damage == "none":
        assert checked["accepted"] is True
        assert checked["text"] == text
        assert checked["live_authority_verified"] is True
        assert checked["daemon_instance_id"] == "instance"
        assert checked["record_sha256"] == record["record_sha256"]
    else:
        assert checked["accepted"] is False
        assert "text" not in checked
        assert checked["must_not_replay"] is True
