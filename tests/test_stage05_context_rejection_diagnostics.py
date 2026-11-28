"""Canonical pre-dispatch refusal retains bounded diagnostics without host authority."""
from latka_jazn.core.model_transport_failure import (
    ollama_context_rejection,
    ollama_terminal_attempt_failure,
    terminal_local_model_failure,
    model_failure_projection,
)


def test_context_refusal_is_one_canonical_bounded_failure() -> None:
    code = "local_context_required_truth_sections_overflow"
    response = {
        "adapter_id": "local_llm_adapter",
        "provider": "ollama",
        "generated": False,
        "status": "context_rejected",
        "text": "PRIVATE_CANARY",
        "transport": {
            "error_code": code,
            "attempts": [
                {"request_dispatched": True, "eval_count": 1, "text": "PRIVATE_OLD"},
                {"request_dispatched": True, "eval_count": 2, "text": "PRIVATE_PRIOR"},
                {
                    "status": "context_rejected",
                    "error_code": code,
                    "fallback_required": True,
                    "request_dispatched": False,
                    "num_predict": 800,
                    "ollama_num_ctx": 8192,
                    "eval_count": -1,
                    "done_reason": "PRIVATE_REASON",
                    "prompt": "PRIVATE_PROMPT",
                },
            ],
        },
    }
    expected = {
        "provider": "ollama",
        "adapter_id": "local_llm_adapter",
        "error_code": code,
        "failure_kind": "context_rejection",
        "request_dispatched": False,
        "prior_attempt_dispatched": True,
        "automatic_retry_allowed": False,
        "host_generation_authorized": False,
        "adapter_status": "context_rejected",
        "attempts": [
            {"request_dispatched": True, "eval_count": 2},
            {"request_dispatched": False, "num_predict": 800, "ollama_num_ctx": 8192},
        ],
    }
    assert ollama_context_rejection(response) == expected
    assert ollama_terminal_attempt_failure(response) == expected
    decision = {
        "model_executor_preflight": {"executor": "local_model"},
        "model_generated": False,
        "requires_host_model": True,
        "model_guided_synthesis": {"used": False, "adapter_response": response},
    }
    failure = terminal_local_model_failure(decision)
    assert failure is not None
    assert failure == expected
    assert model_failure_projection(failure) == (
        "model_context_rejection", "local_model_context_rejected",
    )
    assert "PRIVATE_" not in repr(failure)
    decision["model_generated"] = True
    assert terminal_local_model_failure(decision) is None
