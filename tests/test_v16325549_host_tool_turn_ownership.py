from __future__ import annotations

from latka_jazn.core.turn_authority_runtime_overlay import install_turn_authority_runtime_overlay

# Match the canonical run.py entrypoint before importing bridge helpers. This
# prevents pytest collection order from retaining pre-overlay function objects.
install_turn_authority_runtime_overlay()

from latka_jazn.core.host_response_candidate_guard import build_host_generation_context
from latka_jazn.core.host_tool_turn_policy import build_host_tool_turn_policy, validate_tool_evidence_against_policy
from latka_jazn.core.model_context_compiler import compile_model_context
from latka_jazn.core.nlg_planner import build_nlg_plan
from latka_jazn.core.operational_thought_frame import build_operational_thought_frame


def test_web_tool_is_subordinate_to_runtime_turn() -> None:
    user = "Wyszukaj w sieci aktualne źródła i sprawdź je."
    frame = {"turn_response_policy": {"external_research_required": True}}
    plan = build_nlg_plan(
        user_text=user,
        cognitive_frame=frame,
        response_policy={"external_research_required": True},
        route="external_research",
        detected_intent="research",
    )
    thought = build_operational_thought_frame(
        user_text=user, nlg_plan=plan, cognitive_frame=frame, response_policy={"external_research_required": True}
    )
    model_context = compile_model_context(
        user_text=user,
        cognitive_frame=frame,
        nlg_plan=plan,
        thought_frame=thought,
        response_policy={"external_research_required": True},
    ).to_dict()
    contract = build_host_generation_context(model_context, detected_intent="research", route="external_research")
    policy = contract["host_tool_turn_policy"]
    assert policy["runtime_owns_turn"] is True
    assert policy["tool_results_cannot_be_voice_source"] is True
    assert policy["finalization_required_after_tool_use"] is True
    assert "web.run" in policy["allowed_tools"]


def test_image_generation_is_planned_as_host_capability_not_voice() -> None:
    policy = build_host_tool_turn_policy(
        user_text="Zobrazuj tę scenę i wygeneruj obraz.",
        detected_intent="creative",
        route="creative_or_document",
        nlg_plan={"source_policy": "runtime_only"},
    )
    assert "image_gen" in policy["allowed_tools"]
    assert policy["tool_output_may_be_visible_without_runtime_finalization"] is False
    assert policy["tool_results_cannot_be_voice_source"] is True


def test_unplanned_external_tool_evidence_is_rejected() -> None:
    policy = build_host_tool_turn_policy(
        user_text="Porozmawiaj ze mną.", detected_intent="ordinary_conversation", route="ordinary_dialogue", nlg_plan={}
    )
    violations = validate_tool_evidence_against_policy(
        [{"tool": "web.run", "operation": "search", "source_refs": ["turn1search1"], "source_urls": []}],
        policy,
    )
    assert "tool_not_authorized_for_turn:web.run" in violations
