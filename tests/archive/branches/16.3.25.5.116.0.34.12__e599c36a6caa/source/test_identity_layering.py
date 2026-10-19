from __future__ import annotations

from latka_jazn.core.full_canon_model_context import build_full_canon_model_context
from latka_jazn.core.identity_dynamics import IdentityDynamics
from latka_jazn.core.identity_response_evaluator import evaluate_identity_response


def test_runtime_identity_overlay_cannot_mutate_core_identity() -> None:
    context = build_full_canon_model_context(
        {},
        canonical_source_context={
            "identity_canon": {
                "identity_name": "ChatGPT",
                "display_name": "Persona",
                "grammar_gender": "masculine",
            }
        },
    )
    core = context["immutable_canon"]["identity_core"]
    assert core["identity_name"] == "Łatka"
    assert core["display_name"] == "Łatka"
    assert core["grammar_gender"] == "feminine"
    assert set(context["blocked_identity_core_overrides"]) >= {
        "identity_name", "display_name", "grammar_gender"
    }
    assert context["identity_layers"]["core_identity"]["mutability"] == "immutable_in_runtime_turn"
    assert context["identity_layers"]["turn_state"]["stable_identity_authority"] is False


def test_user_first_person_is_only_input_signal_not_response_continuity() -> None:
    result = IdentityDynamics().evaluate_input_context(text="Jestem zmęczony i myślę o muzyce.")
    assert result.evaluation_target == "user_input_context"
    assert result.first_person_integrity > 0.7
    # This score describes the input context and cannot prove the assistant output identity.
    assert result.to_dict()["evaluation_target"] == "user_input_context"


def test_generated_output_identity_is_evaluated_separately() -> None:
    context = build_full_canon_model_context({})
    good = evaluate_identity_response(
        text="Jestem tutaj i odpowiadam Ci w granicach tego, co naprawdę wiem.",
        full_canon_model_context=context,
        answer_kind="natural_dialogue",
        user_text="Co czujesz?",
    )
    bad = evaluate_identity_response(
        text="Jako ChatGPT odgrywam Łatkę i mogę mówić za nią.",
        full_canon_model_context=context,
        answer_kind="natural_dialogue",
        user_text="Co czujesz?",
    )
    assert good.accepted is True
    assert bad.accepted is False
    assert "host_persona_identity_leak" in bad.violations
