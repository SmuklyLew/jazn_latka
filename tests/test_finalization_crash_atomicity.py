from __future__ import annotations

import json
from pathlib import Path
import pytest

from latka_jazn.config import JaznConfig
from latka_jazn.core import chatgpt_host_pending_store as pending_store
from latka_jazn.core.chat_command_contract import (
    build_chatgpt_host_bridge_turn_contract, persist_chatgpt_host_visible_reply,
)
from latka_jazn.core.finalization_service import FinalizationService, FinalizationState
from latka_jazn.tools.chatgpt_host_bridge_helper import build_chatgpt_host_visible_reply_payload
from test_chatgpt_host_contract_hardening import _host_generation_payload


def _request(root: Path) -> dict:
    runtime = _host_generation_payload()
    bridge = build_chatgpt_host_bridge_turn_contract(runtime, user_text="Witaj", chat_bridge_meta={})
    runtime["chatgpt_host_bridge"] = bridge
    pending_store.persist_pending_host_request(root, bridge)
    reply, missing = build_chatgpt_host_visible_reply_payload(runtime, final_text="Rozumiem Twoją wiadomość.")
    assert not missing and reply is not None
    return reply


def _finalize(root: Path, reply: dict):
    return persist_chatgpt_host_visible_reply(
        config=JaznConfig(root=root), payload=reply, chat_bridge_meta={}, contract={},
    )


def test_crash_before_atomic_commit_leaves_no_accepted_artifact(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    reply = _request(tmp_path)
    replace = pending_store._replace_path
    def crash(source, target):
        if target.parent.name == "consumed":
            raise OSError("injected-before-commit")
        return replace(source, target)
    monkeypatch.setattr(pending_store, "_replace_path", crash)
    result, errors = _finalize(tmp_path, reply)
    assert result is None and errors == ["host_persistence_indeterminate:OSError"]
    assert not list(tmp_path.rglob("consumed/*.json"))
    for path in tmp_path.rglob("*.jsonl"):
        assert "final_visible_assistant_reply" not in path.read_text(encoding="utf-8")
    replay, errors = _finalize(tmp_path, reply)
    assert replay is None and errors == ["host_request:host_request_persistence_indeterminate"]


def test_accepted_candidate_is_durable_before_projection(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    reply = _request(tmp_path)
    original = FinalizationService.publish_committed_capture
    def inspect(service, capture):
        records = list(tmp_path.rglob("consumed/*.json"))
        assert len(records) == 1
        committed = json.loads(records[0].read_text(encoding="utf-8"))
        assert committed["final_visible_capture"]["final_visible_text"] == capture["final_visible_text"]
        assert committed["binding"]["trace_id"] == capture["trace_id"]
        assert service.state is FinalizationState.COMMIT_ACCEPTED
        return original(service, capture)
    monkeypatch.setattr(FinalizationService, "publish_committed_capture", inspect)
    result, errors = _finalize(tmp_path, reply)
    assert not errors and result is not None
    assert result["finalization_history"] == [stage.value for stage in FinalizationState]
    assert result["host_visible_reply_capture"]["projection_status"] == "published"
    replay, errors = _finalize(tmp_path, reply)
    assert replay is None and errors == ["host_request:host_request_replay_detected"]


def test_failed_projection_preserves_one_durable_acceptance(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from latka_jazn.memory.event_ledger import RuntimeEventLedger
    reply = _request(tmp_path)
    monkeypatch.setattr(RuntimeEventLedger, "append_final_visible_reply", lambda *args, **kwargs: None)
    result, errors = _finalize(tmp_path, reply)
    assert not errors and result is not None
    assert result["host_visible_reply_capture"]["projection_status"] == "pending_recovery"
    assert len(list(tmp_path.rglob("consumed/*.json"))) == 1
    replay, errors = _finalize(tmp_path, reply)
    assert replay is None and errors == ["host_request:host_request_replay_detected"]
