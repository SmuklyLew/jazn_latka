from latka_jazn.core.reasoning_orchestrator import ReasoningOrchestrator


def test_simple_dialogue_uses_fast_lane() -> None:
    plan = ReasoningOrchestrator().plan(
        user_text="Hej, co słychać?",
        intent="ordinary_conversation",
        classifier_confidence=0.92,
    )
    assert plan.mode == "fast"
    assert plan.requires_tools is False
    assert plan.consider_alternatives is False


def test_architecture_update_uses_deliberative_verified_lane() -> None:
    plan = ReasoningOrchestrator().plan(
        user_text="Przygotuj pełną architekturę, sprawdź wszystko, zaktualizuj kod i zweryfikuj bez regresji.",
        intent="system_update_execution_request",
        classifier_confidence=0.83,
        tool_available=True,
    )
    assert plan.mode == "deliberative"
    assert plan.requires_tools is True
    assert plan.requires_verification is True
    assert "verify_result_against_goal_and_truth_boundary" in plan.operational_steps
    assert "private" not in " ".join(plan.operational_steps).lower()
