"""Cognitive development P0B–P4: source-free contract tests and ablations."""
from __future__ import annotations

from hashlib import sha256
import math
import pytest

from latka_jazn.core.cognitive_development_evaluation import (
    IntentCase, SourceClaim, assess_source_claim, calibration_metrics,
    evaluate_intents, regulate_with_ablation, rest_safety_contract_probe,
    synthetic_operator_report,
)


def test_p0b_route_discriminates_code_audit_from_zip_status() -> None:
    scores = evaluate_intents([
        IntentCase("audit", "Przeanalizuj kod źródłowy Jaźni z master i ZIP. "
                   "Opisz architekturę Łatki.", "self_architecture_audit_request",
                   "Czy paczka ZIP Jaźni działa?"),
        IntentCase("write", "Napraw teraz kod systemu Jaźni na nowym branchu.",
                   "system_update_execution_request"),
    ])
    assert scores["accuracy"] == 1.0, scores["observations"]


def test_p0b_records_incorrect_predictions_without_fake_success() -> None:
    scores = evaluate_intents([IntentCase("control", "Czy jaźń działa?", "wrong")])
    assert scores["correct"] == 0
    assert scores["observations"][0]["matched"] is False
    assert scores["claim_of_generalization_allowed"] is False
    with pytest.raises(ValueError):
        evaluate_intents([])


def test_p1_typed_source_has_digest_and_lineage_but_not_db_readiness() -> None:
    content = "synthetic conversation example"
    source = SourceClaim(content, sha256(content.encode()).hexdigest(),
                         "fixture-turn-1", "conversation_archive", ("fixture-source-1",))
    result = assess_source_claim(source, query="Przypomnij sobie naszą rozmowę.")
    assert result["allowed_for_candidate_consideration"] is True
    assert result["db_presence_verified"] is False
    assert result["autobiographical_recall_verified"] is False
    broken = SourceClaim(content + "tampered", source.expected_sha256,
                         source.source_id, source.semantic_source_type, source.lineage)
    assert "digest_mismatch" in assess_source_claim(
        broken, query="Przypomnij sobie naszą rozmowę.")["reason_codes"]


@pytest.mark.parametrize("source_type", [
    "synthetic_dream", "derived_reflection", "derived_semantic",
    "inference", "diagnostic_test",
])
def test_p1_derived_and_synthetic_never_certify_primary(source_type: str) -> None:
    claim = SourceClaim("fixture", sha256(b"fixture").hexdigest(),
                        "source-1", source_type, ("origin-1",))
    decision = assess_source_claim(claim, query="Przypomnij sobie naszą rozmowę.")
    assert decision["allowed_for_candidate_consideration"] is False
    assert "derived_cannot_be_primary" in decision["reason_codes"]


def test_p1_missing_lineage_refuses_even_matched_digest() -> None:
    claim = SourceClaim("fixture", sha256(b"fixture").hexdigest(),
                        "source-1", "conversation_archive", ())
    result = assess_source_claim(claim, query="Przypomnij sobie naszą rozmowę.")
    assert result["allowed_for_candidate_consideration"] is False
    assert "source_lineage_missing" in result["reason_codes"]


def test_p2_regulator_has_bounded_causal_effect() -> None:
    result = regulate_with_ablation()
    assert result["bounded_downstream_effect_observed"] is True
    assert result["high_risk_tool_budget"] < result["baseline_tool_budget"]


def test_p3_brier_and_ece_are_measured_not_called_calibration() -> None:
    report = calibration_metrics([(0.75, 1), (0.25, 0)])
    assert report["brier_score"] == 0.0625
    assert report["calibration_ready"] is False
    for invalid in [(float("nan"), 1), (1.5, 1), (0.5, True)]:
        with pytest.raises(ValueError):
            calibration_metrics([invalid])


def test_p3_rest_defaults_block_auto_l3_and_external_actions() -> None:
    status = rest_safety_contract_probe()
    assert status["automatic_l3_allowed"] is False
    assert status["external_tool_authority"] is False
    assert status["live_rest_executed"] is False


def test_p4_report_is_source_free_and_read_only() -> None:
    report = synthetic_operator_report()
    assert report["runtime_mutated"] is False
    assert report["memory_mutated"] is False
    assert report["real_memory_attached"] is False
    assert report["live_chatgpt_verified"] is False
    assert report["p1_synthetic_fixture"]["allowed_for_candidate_consideration"] is False
    assert report["p2_homeostasis"]["bounded_downstream_effect_observed"] is True
