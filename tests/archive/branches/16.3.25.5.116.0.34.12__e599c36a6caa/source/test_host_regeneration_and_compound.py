"""v16.3.25.5.115.8: same-request repair and retrospective subintent gates."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

import latka_jazn.core.host_finalization_transaction as tx
from latka_jazn.core.host_regeneration_policy import decide_host_regeneration
from latka_jazn.nlp.utterance_components import analyse_utterance


@pytest.mark.parametrize("violation", [
    "memory_claim_without_allowed_memory_payload",
    "memory_claim_without_grounded_items",
    "self_state_question_missing_operational_state",
    "missing_required_components_for_intent",
    "compound_component_coverage_incomplete",
])
def test_one_bounded_semantic_rewrite_is_permitted(violation: str) -> None:
    first = decide_host_regeneration([violation], attempts_used=0, max_attempts=1)
    exhausted = decide_host_regeneration([violation], attempts_used=1, max_attempts=1)
    assert first.regenerate is True
    assert first.reason == "host_candidate_semantic_retry"
    assert exhausted.regenerate is False
    assert exhausted.reason == "regeneration_budget_exhausted"


@pytest.mark.parametrize("violation", [
    "full_canon_context_missing_or_invalid",
    "used_memory_id_not_in_grounded_payload",
    "host_generation_context_sha256_mismatch",
])
def test_integrity_and_provenance_violations_remain_non_regenerable(violation: str) -> None:
    decision = decide_host_regeneration([violation], attempts_used=0, max_attempts=1)
    assert decision.regenerate is False
    assert decision.reason == "non_regenerable_finalization_violation"


def test_retrospective_dialogue_is_preserved_as_second_semantic_goal() -> None:
    report = analyse_utterance(
        "Jak się czujesz od naszej ostatniej dłużej rozmowy?"
    )
    assert any(
        "self_affect" in item.semantic_intents
        and "memory_recall" in item.semantic_intents
        and item.memory_required
        for item in report.question_components
    )


def test_semantic_rejection_reuses_same_binding_without_display(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called: list[tuple[str, str]] = []
    monkeypatch.setattr(
        tx,
        "request_host_regeneration",
        lambda root, *, turn_id, reason: (
            called.append((turn_id, reason))
            or {
                "binding": {
                    "turn_id": "turn-1",
                    "trace_id": "trace-1",
                    "host_request_contract_hash": "hash-1",
                },
                "generation_context": {
                    "host_generation_context": {"context_sha256": "context-hash"},
                    "host_generation_rules": ["follow source boundaries"],
                },
                "request_contract_hash": "hash-1",
                "regeneration_attempts": 1,
                "max_regeneration_attempts": 1,
            }
        ),
    )
    ports = tx.HostFinalizationPorts(
        extract_payload=lambda _: ({}, []),
        presentation=lambda result: {
            "action": "generate_then_finalize",
            "chatgpt_host_bridge": result["chatgpt_host_bridge"],
        },
        commit_conversation=lambda **_: {},
        commit_session=lambda **_: {},
    )
    result, errors = tx._request_repair_or_reject(
        config=type("Cfg", (), {"root": Path("/unused")})(),
        ports=ports,
        pending={"regeneration_attempts": 0, "max_regeneration_attempts": 1},
        reply={"turn_id": "turn-1"},
        binding={"turn_id": "turn-1", "trace_id": "trace-1"},
        chat_bridge_meta={"mode": "mcp"},
        contract={"schema_version": "test"},
        violation_codes=["missing_required_components_for_intent"],
        error_prefix="host_candidate",
        finalization_payload=None,
    )
    assert errors == []
    assert result is not None
    assert result["chatgpt_host_presentation"]["action"] == "generate_then_finalize"
    assert result["chatgpt_host_bridge"]["turn_id"] == "turn-1"
    assert result["chatgpt_host_bridge"]["trace_id"] == "trace-1"
    assert result["host_regeneration"]["attempt"] == 1
    assert called == [("turn-1", "host_candidate_semantic_retry")]


def test_retry_exhaustion_does_not_create_a_new_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    released: list[str] = []
    monkeypatch.setattr(
        tx, "release_claimed_host_request",
        lambda root, *, turn_id: released.append(turn_id),
    )
    result, errors = tx._request_repair_or_reject(
        config=type("Cfg", (), {"root": Path("/unused")})(),
        ports=tx.HostFinalizationPorts(
            extract_payload=lambda _: ({}, []),
            presentation=lambda result: {},
            commit_conversation=lambda **_: {},
            commit_session=lambda **_: {},
        ),
        pending={"regeneration_attempts": 1, "max_regeneration_attempts": 1},
        reply={"turn_id": "turn-1"},
        binding={"turn_id": "turn-1"},
        chat_bridge_meta={},
        contract={},
        violation_codes=["memory_claim_without_grounded_items"],
        error_prefix="host_candidate",
        finalization_payload=None,
    )
    assert result is None
    assert "host_regeneration:host_regeneration_budget_exhausted" in errors
    assert released == ["turn-1"]
