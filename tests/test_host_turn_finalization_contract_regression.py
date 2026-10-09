"""Cross-phase regression for dynamically installed host authority contracts."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from latka_jazn.core import host_response_candidate_guard, host_finalization_transaction
from latka_jazn.core.model_guided_response_synthesizer import ModelGuidedResponseSynthesizer
from latka_jazn.core.model_executor_preflight import ModelExecutorPreflight
from latka_jazn.core.turn_authority_runtime_overlay import install_turn_authority_runtime_overlay
from latka_jazn.core.turn_pipeline_contract import (
    build_turn_pipeline_contract,
    finalize_turn_pipeline_contract,
    validate_turn_pipeline_contract,
)


HASH = "a" * 64


def _pipeline(context: dict, *, requires_host: bool) -> dict:
    return build_turn_pipeline_contract(
        turn_id="turn-regression",
        trace_id="trace-regression",
        user_text_sha256=HASH,
        identity_canon_sha256=HASH,
        host_generation_context=context,
        requires_host_generation=requires_host,
        runtime_final_available=not requires_host,
    )


def test_phase1_synthesizer_resolves_installed_overlay_after_import(monkeypatch) -> None:
    # The class is imported BEFORE the overlay is installed, reproducing the
    # previously broken direct-function import and module-caching order.
    install_turn_authority_runtime_overlay()
    monkeypatch.setattr(
        ModelGuidedResponseSynthesizer,
        "_build_context",
        staticmethod(lambda **kwargs: {"user_text": kwargs["user_text"], "nlg_plan": {}}),
    )
    result = ModelGuidedResponseSynthesizer().synthesize(
        adapter=SimpleNamespace(describe=lambda: {"name": "chatgpt_runtime_adapter"}),
        user_text="Sprawdź kontrakty finalizacji.",
        draft_body="",
        detected_intent="system_diagnostic_question",
        route="runtime_diagnostic",
        cognitive_frame={},
        response_policy={},
        executor_preflight=ModelExecutorPreflight(
            executor="host_bridge",
            available=True,
            retry_allowed=False,
            adapter_id="chatgpt_runtime_adapter",
            provider="chatgpt_host",
            model="host_managed",
            reason="host_visible_generation_requires_external_handoff",
        ),
    )
    context = result.host_generation_context
    assert context is not None
    assert host_response_candidate_guard.validate_host_generation_context(context)
    policy = context["host_tool_turn_policy"]
    assert policy["runtime_owns_turn"] is True
    assert policy["tool_results_cannot_be_voice_source"] is True
    assert validate_turn_pipeline_contract(_pipeline(context, requires_host=True))["ok"] is True


def test_missing_or_malformed_policy_fails_closed_in_both_phases() -> None:
    pending = _pipeline({}, requires_host=True)
    validation = validate_turn_pipeline_contract(pending)
    assert validation["ok"] is False
    assert "host_tool_turn_policy_missing" in validation["violations"]
    assert "host_tool_authorization_incomplete" in validation["violations"]

    finalized = finalize_turn_pipeline_contract(pending)
    assert finalized["host_generation_required"] is True
    assert validate_turn_pipeline_contract(finalized)["ok"] is False

    invalid = _pipeline({"host_tool_turn_policy": {
        "runtime_owns_turn": True,
        "tool_results_cannot_be_voice_source": True,
        "finalization_required_after_tool_use": True,
        "same_turn_resume_required": False,
        "accepted_visible_turn_required": True,
        "message_envelope_required": True,
        "tool_output_may_be_visible_without_runtime_finalization": False,
    }}, requires_host=True)
    assert invalid["stages"]["tool_authorization"] == "degraded"
    failures = validate_turn_pipeline_contract(invalid)["violations"]
    assert "host_tool_policy_requirement_missing:same_turn_resume_required" in failures


def test_exact_runtime_final_does_not_require_host_tool_policy() -> None:
    assert validate_turn_pipeline_contract(_pipeline({}, requires_host=False))["ok"] is True


def test_phase2_evaluator_dispatch_is_late_bound(monkeypatch) -> None:
    install_turn_authority_runtime_overlay()
    sentinel = {"accepted": False, "violations": ["authority_guard_is_live"]}
    monkeypatch.setattr(
        host_response_candidate_guard, "evaluate_host_response_candidate",
        lambda **kwargs: sentinel,
    )
    assert host_finalization_transaction.evaluate_host_response_candidate(
        final_text="test", host_generation_context={}, used_memory_item_ids=[],
    ) is sentinel


def test_contract_index_paths_are_real() -> None:
    root = Path(__file__).resolve().parents[1]
    index = root / "docs/runtime/TURN_FINALIZATION_CONTRACTS.md"
    assert index.is_file()
    assert "TURN_FINALIZATION_CONTRACTS.md" in (root / "AGENTS.md").read_text(encoding="utf-8")
    assert "TURN_FINALIZATION_CONTRACTS.md" in (root / "docs/README.md").read_text(encoding="utf-8")
    assert "TURN_FINALIZATION_CONTRACTS.md" in (root / "README.md").read_text(encoding="utf-8")
    assert "TURN_FINALIZATION_CONTRACTS.md" in (root / "docs/runtime/CHATGPT_HOST_FINALIZATION_PROTOCOL_TEST_MATRIX.md").read_text(encoding="utf-8")
    for rel in ("latka_jazn/core/model_guided_response_synthesizer.py",
                "latka_jazn/core/host_finalization_transaction.py",
                "latka_jazn/core/turn_pipeline_contract.py"):
        assert (root / rel).is_file()
        assert Path(rel).name in index.read_text(encoding="utf-8")
