from __future__ import annotations

from latka_jazn.core.host_response_candidate_guard import validate_external_tool_evidence
from latka_jazn.core.response_candidate import ResponseCandidate
from latka_jazn.core.response_candidate_evaluator import evaluate_response_candidate


def _candidate() -> ResponseCandidate:
    return ResponseCandidate(
        candidate_id="host",
        text="Odpowiedź oparta na sprawdzonych źródłach.",
        source="model_adapter",
        provider="chatgpt_host",
        model="host_managed",
        status="completed",
        used_memory_item_ids=[],
        generation_reason="test",
    )


def test_external_tool_evidence_is_bounded_and_fail_closed() -> None:
    valid = validate_external_tool_evidence(
        [
            {
                "tool": "web.run",
                "operation": "search",
                "source_refs": ["turn4search2"],
                "source_urls": ["https://www.python.org/doc/"],
            }
        ]
    )
    assert valid["ok"] is True
    assert valid["evidence"][0]["tool"] == "web.run"

    missing = validate_external_tool_evidence([])
    assert missing["ok"] is False
    invalid = validate_external_tool_evidence(
        [{"tool": "made.up", "operation": "search", "source_refs": ["not-a-ref"]}]
    )
    assert invalid["ok"] is False
    assert any(error.startswith("tool_not_allowed") for error in invalid["errors"])


def test_generic_model_still_cannot_fake_web_but_host_attestation_can_satisfy_policy() -> None:
    plan = {"source_policy": "requires_external_web"}
    context = {"nlg_plan": plan, "allowed_memory_items": []}
    blocked = evaluate_response_candidate(
        candidate=_candidate(),
        nlg_plan=plan,
        model_context=context,
        response_policy={"exact_runtime_required": False},
    )
    assert "model_candidate_cannot_fake_external_web_sources" in blocked.violations

    attested = evaluate_response_candidate(
        candidate=_candidate(),
        nlg_plan=plan,
        model_context=context,
        response_policy={
            "exact_runtime_required": False,
            "external_web_evidence_accepted": True,
        },
    )
    assert "model_candidate_cannot_fake_external_web_sources" not in attested.violations
    assert "host_external_web_evidence_accepted" in attested.reasons
