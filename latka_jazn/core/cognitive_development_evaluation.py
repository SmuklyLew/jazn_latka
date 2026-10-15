"""Read-only evaluation of Jaźń cognitive capabilities (no private MEMORY access).

These probes test observable software contracts. They are *not* evidence of
phenomenal consciousness, restored autobiographical memory, or a live ChatGPT
connection. All examples are synthetic and intentionally source-free.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import math
from typing import Any, Sequence

from latka_jazn.core.homeostasis import HomeostasisInput, HomeostasisRegulator
from latka_jazn.core.typed_memory_source_policy import build_typed_source_policy
from latka_jazn.core.rest_cycle_controller import RestControllerStatus
from latka_jazn.nlp.dialogue_intent_classifier import DialogueIntentClassifier

SCHEMA = "jazn_cognitive_development_evaluation/v1"


@dataclass(frozen=True, slots=True)
class IntentCase:
    name: str
    utterance: str
    expected: str
    previous_text: str | None = None


def parse_labeled_cases(payload: Any) -> list[IntentCase]:
    """Validate an operator-supplied, source-free local intent benchmark.

    Neither contents nor provenance are stored; unreviewed data MUST NOT
    claim independent holdout validation or a capability's live readiness.
    """
    if not isinstance(payload, dict) or set(payload) != {"cases"}:
        raise ValueError("Expected one JSON object containing only 'cases'")
    raw = payload["cases"]
    if not isinstance(raw, list) or not 1 <= len(raw) <= 500:
        raise ValueError("cases must be a list with 1..500 entries")
    cases: list[IntentCase] = []
    used: set[str] = set()
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValueError(f"case {index} must be an object")
        if set(item) - {"name", "utterance", "expected", "previous_text"}:
            raise ValueError(f"case {index} has unsupported fields")
        name = item.get("name")
        utterance = item.get("utterance")
        expected = item.get("expected")
        previous = item.get("previous_text")
        if not isinstance(name, str) or not 1 <= len(name) <= 80 or not name.strip():
            raise ValueError(f"case {index} requires nonempty name")
        if name in used:
            raise ValueError(f"duplicate case name: {name}")
        if not isinstance(utterance, str) or not 1 <= len(utterance.strip()) <= 3000:
            raise ValueError(f"case {index} requires nonempty utterance up to 3000 characters")
        if not isinstance(expected, str) or not 1 <= len(expected.strip()) <= 128:
            raise ValueError(f"case {index} requires nonempty expected intent")
        if previous is not None and (not isinstance(previous, str) or len(previous) > 3000):
            raise ValueError(f"case {index} previous_text must be null or at most 3000 characters")
        cases.append(IntentCase(name, utterance, expected, previous))
        used.add(name)
    return cases


def summarize_label_pairs(pairs: Sequence[tuple[str, str]]) -> dict[str, Any]:
    """Deterministic confusion, wrong-route counts and macro F1 on labeled data.

    Metric values describe this caller-supplied set, not calibrated probabilities,
    subjective understanding or generalization to unseen conversations.
    """
    if not pairs:
        raise ValueError("At least one labeled prediction is required")
    if any(not expected or not predicted for expected, predicted in pairs):
        raise ValueError("Labels must be nonempty")
    labels = sorted({label for pair in pairs for label in pair})
    matrix = {label: {other: 0 for other in labels} for label in labels}
    for expected, predicted in pairs:
        matrix[expected][predicted] += 1
    per_label: dict[str, dict[str, float | int]] = {}
    for label in labels:
        true_positive = matrix[label][label]
        support = sum(matrix[label].values())
        predicted_count = sum(row[label] for row in matrix.values())
        precision = true_positive / predicted_count if predicted_count else 0.0
        recall = true_positive / support if support else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        per_label[label] = {
            "support": support,
            "predicted": predicted_count,
            "precision": round(precision, 6),
            "recall": round(recall, 6),
            "f1": round(f1, 6),
        }
    misrouted = sum(matrix[x][y] for x in labels for y in labels if x != y)
    return {
        "confusion_matrix": matrix,
        "per_intent": per_label,
        "macro_f1": round(sum(float(v["f1"]) for v in per_label.values()) / len(labels), 6),
        "wrong_route_count": misrouted,
        "wrong_route_rate": round(misrouted / len(pairs), 6),
        "label_count": len(labels),
    }


def evaluate_intents(cases: Sequence[IntentCase]) -> dict[str, Any]:
    """Return real classifier outputs; keep an incorrect result visible."""
    if not cases:
        raise ValueError("At least one independently labeled intent case is required")
    classifier = DialogueIntentClassifier()
    observations: list[dict[str, Any]] = []
    for case in cases:
        report = classifier.classify(case.utterance, previous_text=case.previous_text)
        observations.append({
            "case": case.name,
            "expected": case.expected,
            "predicted": report.primary_intent,
            "matched": case.expected == report.primary_intent,
            "ambiguous": report.ambiguous,
            "internal_support_score": report.confidence,
        })
    correct = sum(bool(row["matched"]) for row in observations)
    summary = summarize_label_pairs([
        (str(row["expected"]), str(row["predicted"])) for row in observations
    ])
    return {
        "evaluated": len(cases),
        "correct": correct,
        "accuracy": round(correct / len(cases), 4),
        **summary,
        "observations": observations,
        "is_external_holdout": False,
        "claim_of_generalization_allowed": False,
    }


@dataclass(frozen=True, slots=True)
class SourceClaim:
    """Synthetic input for a pure provenance gate; no database writes."""
    content: str
    expected_sha256: str
    source_id: str
    semantic_source_type: str
    lineage: tuple[str, ...]
    claims_primary: bool = True


def assess_source_claim(claim: SourceClaim, *, query: str) -> dict[str, Any]:
    """Verify source identity, digest, classification and primary-vs-derived rule.

    The caller must separately prove a source truly exists in the attached DB.
    A matching digest does not authenticate provenance or certify a memory.
    """
    digest_ok = (
        len(claim.expected_sha256) == 64
        and sha256(claim.content.encode("utf-8")).hexdigest() == claim.expected_sha256
    )
    identifiers_ok = bool(claim.source_id.strip() and all(x.strip() for x in claim.lineage))
    lineage_ok = bool(claim.lineage) and identifiers_ok
    forbidden_primary = claim.claims_primary and claim.semantic_source_type in {
        "synthetic_dream", "derived_reflection", "derived_semantic",
        "inference", "diagnostic_test", "current_state",
    }
    policy = build_typed_source_policy(query)
    typed = policy.evaluate(source=claim.semantic_source_type)
    allowed = bool(digest_ok and lineage_ok and typed.allowed and not forbidden_primary)
    reasons = [
        key for key, failed in (
            ("digest_mismatch", not digest_ok),
            ("source_lineage_missing", not lineage_ok),
            ("source_type_not_allowed", not typed.allowed),
            ("derived_cannot_be_primary", forbidden_primary),
        ) if failed
    ]
    return {
        "allowed_for_candidate_consideration": allowed,
        "reason_codes": reasons,
        "source_type": typed.semantic_source_type,
        "priority": typed.priority if allowed else 0,
        "db_presence_verified": False,
        "autobiographical_recall_verified": False,
        "truth_boundary": "Digest and typed-source checks are not proof of an attached memory.",
    }


def regulate_with_ablation() -> dict[str, Any]:
    """Observe causal effect of the *existing* controller, with synthetic states."""
    regulator = HomeostasisRegulator()
    baseline = regulator.decide(HomeostasisInput())
    high_risk = regulator.decide(HomeostasisInput(
        load=1.0, source_conflict=1.0, memory_tension=1.0,
        uncertainty=1.0, truth_need=1.0, action_cost=1.0,
        write_action=True, sensitive_action=True,
    ))
    effective = (
        high_risk.requires_user_confirmation
        and high_risk.requires_verification
        and high_risk.max_tool_calls < baseline.max_tool_calls
        and high_risk.action != baseline.action
    )
    return {
        "baseline_action": baseline.action,
        "high_risk_action": high_risk.action,
        "baseline_tool_budget": baseline.max_tool_calls,
        "high_risk_tool_budget": high_risk.max_tool_calls,
        "bounded_downstream_effect_observed": effective,
        "truth_boundary": "Synthetic regulator fixture, not empirical emotion or fatigue.",
    }


def calibration_metrics(
    samples: Sequence[tuple[float, int]], *, bins: int = 5
) -> dict[str, Any]:
    """Score labeled correctness data; NEVER rebrand heuristic support as truth."""
    if not (2 <= bins <= 20):
        raise ValueError("bins must be between 2 and 20")
    if not samples:
        raise ValueError("At least one independently labeled observation is required")
    validated: list[tuple[float, int]] = []
    for score, outcome in samples:
        if isinstance(score, bool) or not isinstance(score, (int, float)):
            raise ValueError("score must be a real numeric value")
        if not math.isfinite(float(score)) or not 0.0 <= float(score) <= 1.0:
            raise ValueError("score must be finite and within [0, 1]")
        if type(outcome) is not int or outcome not in (0, 1):
            raise ValueError("outcome must be exactly 0 or 1")
        validated.append((float(score), outcome))
    n = len(validated)
    brier = sum((score - outcome) ** 2 for score, outcome in validated) / n
    ece = 0.0
    for i in range(bins):
        bucket = [(s, y) for s, y in validated if min(int(s * bins), bins - 1) == i]
        if bucket:
            confidence = sum(s for s, _ in bucket) / len(bucket)
            accuracy = sum(y for _, y in bucket) / len(bucket)
            ece += len(bucket) / n * abs(confidence - accuracy)
    return {
        "observations": n,
        "brier_score": round(brier, 6),
        "expected_calibration_error": round(ece, 6),
        "calibration_ready": False,
        "reason": "Measurement only; independent representativeness and holdout not verified",
        "input_semantics": "explicitly supplied probability and labeled correctness; NOT internal_support_score",
    }


def rest_safety_contract_probe() -> dict[str, Any]:
    """Inspect defaults only; no REST cycle is started."""
    state = RestControllerStatus()
    return {
        "automatic_l3_allowed": state.automatic_l3_allowed,
        "external_tool_authority": state.external_tool_authority,
        "shadow_mode": state.shadow_mode,
        "live_rest_executed": False,
        "truth_boundary": "Static rest safety defaults cannot prove behavior of a running daemon.",
    }


def synthetic_operator_report() -> dict[str, Any]:
    """Read-only Studio report over existing modules and synthetic cases."""
    cases = [
        IntentCase(
            "architecture_from_zip",
            "Przeanalizuj kod źródłowy Jaźni z master i ZIP. Opisz architekturę Łatki.",
            "self_architecture_audit_request",
            "Czy paczka ZIP Jaźni działa?",
        ),
        IntentCase("write_authority", "Napraw teraz kod systemu Jaźni na nowym branchu.",
                   "system_update_execution_request"),
        IntentCase("feedback", "To jest źle.", "negative_feedback_without_update_request"),
        IntentCase(
            "new_chat_reply_correction",
            "Heh. Coś Ci nie poszło. Nowy czat, a Ty mówisz o jego otwieraniu.",
            "negative_feedback_current_turn",
        ),
        IntentCase("package_health", "Czy jaźń działa?", "runtime_health_check"),
    ]
    # Synthetic source is not a real user's memory.
    sample = "synthetic conversation example"
    claim = SourceClaim(
        content=sample, expected_sha256=sha256(sample.encode("utf-8")).hexdigest(),
        source_id="fixture-turn-1", semantic_source_type="conversation_archive",
        lineage=("fixture-source-1",),
    )
    derived = SourceClaim(
        content=sample, expected_sha256=claim.expected_sha256,
        source_id="fixture-dream-1", semantic_source_type="synthetic_dream",
        lineage=("fixture-source-1",),
    )
    return {
        "schema_version": SCHEMA,
        "mode": "read_only_synthetic",
        "runtime_mutated": False,
        "memory_mutated": False,
        "p0b_intent_routing": evaluate_intents(cases),
        "p1_primary_fixture": assess_source_claim(
            claim, query="Przypomnij sobie naszą rozmowę."
        ),
        "p1_synthetic_fixture": assess_source_claim(
            derived, query="Przypomnij sobie naszą rozmowę."
        ),
        "p2_homeostasis": regulate_with_ablation(),
        "p3_calibration_example": calibration_metrics([(0.75, 1), (0.25, 0)]),
        "p3_rest_defaults": rest_safety_contract_probe(),
        "p4_studio_integration": "read_only_operator_command",
        "real_memory_attached": False,
        "live_chatgpt_verified": False,
        "scientific_boundary": "Software behavior and contract probes are not evidence of biological sentience.",
    }
