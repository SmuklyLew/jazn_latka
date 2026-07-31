from __future__ import annotations

from pathlib import Path

from latka_jazn.core.runtime_activation_cascade import RuntimeActivationCascade
from latka_jazn.core.self_state_runtime import SelfStateRuntime
from latka_jazn.core.turn_execution import TurnExecutionContext


def test_turn_gate_rejects_non_object_integrity_layers() -> None:
    reason = TurnExecutionContext._gate_failure_reason(
        {
            "ok": True,
            "final_visible_text": "visible",
            "final_visible_integrity": ["invalid"],
            "final_visible_integrity_consensus": ["invalid"],
            "runtime_truth_gate": ["invalid"],
        },
        job_status="completed",
    )

    assert reason == "integrity_invalid"


def test_daemon_activation_rejects_invalid_nested_pid(tmp_path: Path) -> None:
    status = RuntimeActivationCascade(tmp_path)._daemon_status(
        {
            "status": {"pid": None},
            "endpoint_ok": True,
            "heartbeat_fresh": True,
        }
    )

    assert status["ok"] is False
    assert status["pid"] is None
    assert status["background_claim_allowed"] is False


def test_self_state_ignores_invalid_dynamic_confidence_values() -> None:
    packet = SelfStateRuntime().build(
        text="test",
        timestamp="2026-07-31T00:00:00+00:00",
        runtime_mode="test",
        intent_tags=["conversation"],
        nlp_report={"average_confidence": {"invalid": True}},
        source_origin={"confidence": ["invalid"]},
    )

    assert packet.confidence == 0.7
