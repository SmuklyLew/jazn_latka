"""Regression: semantic candidate rejection must reach bounded phase-2 retry."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

import latka_jazn.core.host_finalization_transaction as tx


def _host_ports(reply: dict[str, object]) -> tx.HostFinalizationPorts:
    return tx.HostFinalizationPorts(
        extract_payload=lambda _: (reply, []),
        presentation=lambda result: {
            "action": "generate_then_finalize",
            "chatgpt_host_bridge": result["chatgpt_host_bridge"],
        },
        commit_conversation=lambda **_: {},
        commit_session=lambda **_: {},
    )


def test_semantic_gate_rejection_reaches_bounded_retry_without_persisting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transitions: list[object] = []
    service = SimpleNamespace(
        config=SimpleNamespace(root=Path("/unused")),
        transition=lambda state: transitions.append(state),
    )
    binding = {"turn_id": "turn-semantic", "trace_id": "trace-semantic"}
    reply: dict[str, object] = {
        "turn_id": "turn-semantic",
        "trace_id": "trace-semantic",
        "host_request_contract_hash": "request-hash",
        "final_text": "Not accepted.",
    }
    pending = {
        "binding": binding,
        "generation_context": {"host_generation_context": {}},
        "regeneration_attempts": 0,
        "max_regeneration_attempts": 1,
    }
    monkeypatch.setattr(tx, "claim_pending_host_request", lambda root, *, turn_id, request_contract_hash: pending)
    monkeypatch.setattr(
        tx, "evaluate_host_response_candidate",
        lambda **_: {
            "accepted": False,
            "violations": ["missing_required_components_for_intent"],
        },
    )
    calls: list[str] = []

    def regenerate(root: Path, *, turn_id: str, reason: str) -> dict[str, object]:
        calls.append(reason)
        return {
            "binding": binding,
            "generation_context": {"host_generation_context": {}},
            "regeneration_attempts": 1,
            "max_regeneration_attempts": 1,
            "request_contract_hash": "request-hash",
        }

    monkeypatch.setattr(tx, "request_host_regeneration", regenerate)
    monkeypatch.setattr(tx, "finalize_host_visible_text", lambda **_: pytest.fail("must not finalize a rejected candidate"))
    result, errors = tx.finalize_host_candidate(
        service=service,
        ports=_host_ports(reply),
        payload={},
        chat_bridge_meta={},
        contract={},
    )
    assert errors == []
    assert result is not None
    assert result["chatgpt_host_presentation"]["action"] == "generate_then_finalize"
    assert result["chatgpt_host_bridge"]["turn_id"] == "turn-semantic"
    assert "missing_required_components_for_intent" in result["chatgpt_host_bridge"]["regeneration_violations"]
    assert result["chatgpt_host_bridge"]["repair_guidance"]
    assert calls == ["host_candidate_semantic_retry"]


def test_semantic_integrity_failure_is_not_regenerated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    binding = {"turn_id": "turn-invalid", "trace_id": "trace-invalid"}
    reply: dict[str, object] = {
        "turn_id": "turn-invalid",
        "trace_id": "trace-invalid",
        "host_request_contract_hash": "request-hash",
        "final_text": "Invalid.",
    }
    pending = {
        "binding": binding,
        "generation_context": {"host_generation_context": {}},
        "regeneration_attempts": 0,
        "max_regeneration_attempts": 1,
    }
    monkeypatch.setattr(tx, "claim_pending_host_request", lambda root, *, turn_id, request_contract_hash: pending)
    monkeypatch.setattr(
        tx, "evaluate_host_response_candidate",
        lambda **_: {
            "accepted": False,
            "violations": ["full_canon_context_missing_or_invalid"],
        },
    )
    releases: list[str] = []
    monkeypatch.setattr(tx, "release_claimed_host_request", lambda root, *, turn_id: releases.append(turn_id))
    monkeypatch.setattr(tx, "request_host_regeneration", lambda *args, **kwargs: pytest.fail("cannot retry integrity failure"))
    result, errors = tx.finalize_host_candidate(
        service=SimpleNamespace(
            config=SimpleNamespace(root=Path("/unused")),
            transition=lambda state: None,
        ),
        ports=_host_ports(reply),
        payload={},
        chat_bridge_meta={},
        contract={},
    )
    assert result is None
    assert "host_candidate:full_canon_context_missing_or_invalid" in errors
    assert releases == ["turn-invalid"]
