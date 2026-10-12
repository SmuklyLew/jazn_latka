from __future__ import annotations

from latka_jazn.core.nlg_planner import build_nlg_plan
from latka_jazn.core.operational_thought_frame import build_operational_thought_frame
from latka_jazn.core.reasoning_orchestrator import ReasoningOrchestrator


def test_reasoning_plan_requires_identity_and_turn_authority() -> None:
    plan = ReasoningOrchestrator().plan(
        user_text="Sprawdź repo i przygotuj pełną aktualizację.",
        intent="update architecture",
        route="system_update",
        classifier_confidence=0.9,
        source_available=True,
        tool_available=True,
    )
    assert plan.identity_verification_required is True
    assert plan.turn_authority_required is True
    assert plan.tool_plan_required is True
    assert "produce_final_response" in plan.operational_steps


def test_operational_frame_contains_safe_verification_contract_not_private_cot() -> None:
    user = "Sprawdź w sieci i przygotuj aktualizację."
    frame = {"turn_response_policy": {"external_research_required": True}}
    nlg = build_nlg_plan(
        user_text=user,
        cognitive_frame=frame,
        response_policy={"external_research_required": True},
        route="external_research",
        detected_intent="research",
    )
    thought = build_operational_thought_frame(
        user_text=user, nlg_plan=nlg, cognitive_frame=frame, response_policy={"external_research_required": True}
    )
    payload = thought.to_dict()
    assert payload["schema_version"] == "operational_thought_frame/v2"
    assert "identity_response_alignment" in payload["verification_checks"]
    assert "turn_authority_binding_before_visible_output" in payload["verification_checks"]
    assert "runtime_owns_visible_voice" in payload["identity_commitments"]
    assert not any("chain_of_thought" in key for key in payload)
