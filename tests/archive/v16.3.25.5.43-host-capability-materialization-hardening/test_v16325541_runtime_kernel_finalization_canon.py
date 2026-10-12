from __future__ import annotations

import argparse
from dataclasses import FrozenInstanceError
import json
from pathlib import Path
from typing import Any

import pytest

from latka_jazn.cli_commands import host as host_commands
from latka_jazn.core.birth_manifest import BirthEvidence, BirthSourceManifest
from latka_jazn.core.canon import IdentityCanon, LATKA_IDENTITY_KERNEL, load_identity_canon_data
from latka_jazn.core.chat_command_contract import (
    build_chatgpt_host_bridge_turn_contract,
    build_chatgpt_host_presentation_packet,
)
from latka_jazn.core.chatgpt_host_pending_store import (
    calculate_host_request_contract_hash,
    host_request_lifecycle_state,
    persist_pending_host_request,
)
from latka_jazn.core.host_visible_finalization import sha256_host_visible_text
from latka_jazn.version import PACKAGE_RELEASE_NAME, PACKAGE_VERSION


def _bridge(turn_id: str = "turn-v16325541") -> dict[str, Any]:
    runtime: dict[str, Any] = {
        "runtime_version": PACKAGE_VERSION,
        "daemon_request_id": "daemon-request-v16325541",
        "trace": {
            "turn_id": turn_id,
            "trace_id": f"trace-{turn_id}",
            "timestamp_header": "🕒 2026-09-07 19:00:00",
            "timezone": "Europe/Warsaw",
        },
        "conversation_decision": {
            "handler_name": "RuntimeTurnTruthGate",
            "route": "ordinary_dialogue",
            "detected_user_intent": "ordinary_conversation",
            "requires_host_model": True,
            "timestamp_contract": {
                "timezone": "Europe/Warsaw",
                "sample_iso": "2026-09-07T19:00:00+02:00",
                "source": "test",
                "trusted": True,
            },
        },
        "runtime_turn_contract": {
            "turn_id": turn_id,
            "trace_id": f"trace-{turn_id}",
            "handler_name": "RuntimeTurnTruthGate",
            "requires_host_model": True,
            "fallback_classification": "cannot_answer_directly",
            "validation": {"accepted": True},
        },
        "final_response_contract": {
            "turn_id": turn_id,
            "trace_id": f"trace-{turn_id}",
            "runtime_version": PACKAGE_VERSION,
            "requires_host_model": True,
            "timestamp_header": "🕒 2026-09-07 19:00:00",
            "timezone": "Europe/Warsaw",
            "timestamp_sample_iso": "2026-09-07T19:00:00+02:00",
            "timestamp_source": "test",
            "timestamp_trusted": True,
            "author_id": "latka_runtime",
            "author_label": "Łatka",
            "author_source": "jazn_runtime",
            "state_emoticon": "🌿",
        },
        "runtime_truth_gate": {
            "ok": True,
            "normal_response_allowed": False,
            "errors": ["model_guided_speech_required"],
            "degradations": [],
        },
    }
    bridge = build_chatgpt_host_bridge_turn_contract(
        runtime, user_text="Kontynuuj rozmowę.", chat_bridge_meta={}
    )
    bridge["daemon_request_id"] = "daemon-request-v16325541"
    bridge["host_request_contract_hash"] = calculate_host_request_contract_hash(bridge)
    shape = bridge.get("host_reply_jsonl_shape")
    if isinstance(shape, dict):
        shape["host_request_contract_hash"] = bridge["host_request_contract_hash"]
    bridge["pending_request_persisted"] = True
    return bridge


def test_host_presentation_reuses_machine_readable_phase2_binding() -> None:
    bridge = _bridge()
    packet = build_chatgpt_host_presentation_packet({"chatgpt_host_bridge": bridge})

    assert packet["action"] == "generate_then_finalize"
    shape = packet["chatgpt_host_bridge"]["host_reply_jsonl_shape"]
    assert shape["type"] == "host_visible_reply"
    assert shape["turn_id"] == bridge["turn_id"]
    assert shape["trace_id"] == bridge["trace_id"]
    assert shape["host_request_contract_hash"] == bridge["host_request_contract_hash"]
    assert shape["timestamp_header"] == bridge["timestamp_header"]
    assert shape["author_id"] == bridge["author_id"]


def test_canonical_cli_host_finalize_consumes_pending_and_notifies_daemon(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bridge = _bridge()
    persist_pending_host_request(tmp_path, bridge)
    notifications: list[dict[str, Any]] = []

    class FakeEngine:
        def __init__(self, _config: Any) -> None:
            pass

        def shutdown(self) -> None:
            pass

        def persist_final_visible_reply(self, **kwargs: Any) -> dict[str, Any]:
            return {
                "final_visible_text": kwargs["final_text"],
                "turn_id": kwargs["turn_id"],
                "trace_id": kwargs["trace_id"],
            }

    class FakeGateway:
        def __init__(self, _config: Any) -> None:
            pass

        def note_host_finalization(
            self,
            pending: dict[str, Any],
            *,
            outcome: str,
            reason: str,
            terminal: bool = False,
        ) -> dict[str, Any]:
            notifications.append({
                "pending": pending,
                "outcome": outcome,
                "reason": reason,
                "terminal": terminal,
            })
            return {"ok": True, "status": "completed"}

    import latka_jazn.core.engine as engine_module

    monkeypatch.setattr(engine_module, "JaznEngine", FakeEngine)
    monkeypatch.setattr(host_commands, "SecureHostRuntimeGateway", FakeGateway)

    body = "Domykam tę turę przez kanoniczny lifecycle."
    args = argparse.Namespace(
        root=tmp_path,
        text=body,
        text_file=None,
        text_sha256=sha256_host_visible_text(body),
        timestamp_header=bridge["timestamp_header"],
        timezone=bridge["timezone"],
        timestamp_sample_iso=bridge["timestamp_sample_iso"],
        timestamp_source=bridge["timestamp_source"],
        timestamp_trusted=bridge["timestamp_trusted"],
        author_id=bridge["author_id"],
        author_label=bridge["author_label"],
        author_source=bridge["author_source"],
        state_emoticon=bridge["state_emoticon"],
        turn_id=bridge["turn_id"],
        trace_id=bridge["trace_id"],
        host_request_contract_hash=bridge["host_request_contract_hash"],
        supplied_turn_id=None,
        supplied_trace_id=None,
        used_memory_item_id=[],
        external_tool_evidence_file=None,
        daemon_host="127.0.0.1",
        daemon_port=8787,
        max_bytes=2 * 1024 * 1024,
    )

    result = host_commands.finalize_payload(args)

    assert result["accepted"] is True
    assert result["host_finalization_lifecycle_complete"] is True
    assert host_request_lifecycle_state(tmp_path, turn_id=bridge["turn_id"])["state"] == "consumed"
    assert notifications and notifications[-1]["outcome"] == "accepted"
    assert notifications[-1]["terminal"] is True


def test_identity_json_is_audited_but_cannot_override_python_kernel(tmp_path: Path) -> None:
    public_path = tmp_path / "latka_jazn" / "resources" / "canon" / "LATKA_IDENTITY_CANON.json"
    public_path.parent.mkdir(parents=True)
    mirror = dict(LATKA_IDENTITY_KERNEL.to_dict())
    mirror["schema_version"] = "latka_identity_canon/v1"
    mirror["identity_name"] = "Nadpisana-z-JSON"
    public_path.write_text(json.dumps(mirror, ensure_ascii=False), encoding="utf-8")

    private_path = tmp_path / "memory" / "raw" / "LATKA_IDENTITY_CANON.json"
    private_path.parent.mkdir(parents=True)
    private_path.write_text(json.dumps({"identity_name": "Nadpisana-prywatnie"}), encoding="utf-8")

    data = load_identity_canon_data(public_path)

    assert data["identity_name"] == LATKA_IDENTITY_KERNEL.identity_name
    status = data["source_status"]
    assert status["public_mirror_kernel_match"] is False
    assert "identity_name" in status["public_mirror_kernel_mismatches"]
    assert status["private_candidate_present"] is True
    assert status["private_override_loaded"] is False
    assert status["private_override_policy"] == "evidence_only_no_identity_kernel_override"


def test_runtime_identity_object_is_frozen_and_uses_executable_kernel(tmp_path: Path) -> None:
    public_path = tmp_path / "latka_jazn" / "resources" / "canon" / "LATKA_IDENTITY_CANON.json"
    public_path.parent.mkdir(parents=True)
    public_path.write_text(
        json.dumps({**LATKA_IDENTITY_KERNEL.to_dict(), "schema_version": "latka_identity_canon/v1"}, ensure_ascii=False),
        encoding="utf-8",
    )
    canon = IdentityCanon.load(public_path)
    assert canon.kernel is LATKA_IDENTITY_KERNEL
    with pytest.raises(FrozenInstanceError):
        canon.display_name = "inna"  # type: ignore[misc]


def test_birth_source_manifest_has_executable_fail_closed_evaluation() -> None:
    manifest = BirthSourceManifest(PACKAGE_VERSION)
    complete = BirthEvidence(
        one_voice=True,
        active_source=True,
        memory_cycle=True,
        truth_boundary=True,
        learning_from_correction=True,
        conversation_not_diagnostics=True,
        source_trace=True,
    )
    assert manifest.evaluate(complete).status == "pass"
    assert manifest.evaluate({"one_voice": True}).status == "indeterminate"
    failed = manifest.evaluate({**complete.__dict__} if hasattr(complete, "__dict__") else {
        "one_voice": True,
        "active_source": True,
        "memory_cycle": True,
        "truth_boundary": False,
        "learning_from_correction": True,
        "conversation_not_diagnostics": True,
        "source_trace": True,
    })
    assert failed.status == "fail"
    assert manifest.to_dict()["evaluation_contract"]["executable"] is True


def test_release_version_is_bumped_for_runtime_kernel_convergence() -> None:
    assert PACKAGE_VERSION == "16.3.25.5.41"
    assert PACKAGE_RELEASE_NAME == "runtime-kernel-finalization-canon-convergence"
