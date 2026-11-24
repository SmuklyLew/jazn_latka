from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from latka_jazn.config import JaznConfig
from latka_jazn.core.model_guided_response_synthesizer import ModelGuidedSynthesis
from latka_jazn.core.response_pipeline import ResponsePipeline
from latka_jazn.core.turn_pipeline_state import TurnPipelineState, TurnRequest
from latka_jazn.core.runtime_session import JaznRuntimeSession
from latka_jazn.core.source_origin_ledger import SourceOriginLedger


def _synthesis(provider: str, *, generated: bool = True) -> ModelGuidedSynthesis:
    return ModelGuidedSynthesis(
        used=True,
        body="Wypowiedź modelu.",
        status="ok",
        provider=provider,
        model="test-local-model",
        reason="generated",
        sources=[],
        adapter_response={
            "generated": generated,
            "source_origin": "model_adapter",
            "adapter_id": "local_llm_adapter",
            "provider": provider,
            "model": "test-local-model",
            "endpoint_used": "/api/chat",
            "candidate_kind": "model_generated",
        },
    )


def _state(
    *,
    retry_selected: bool = False,
    model_generated: bool = True,
    retry_accepted: bool = True,
    final_accepted: bool = True,
    fallback: str = "not_fallback",
    repaired: bool = False,
) -> TurnPipelineState:
    return TurnPipelineState(
        request=TurnRequest(text="test"),
        model_synthesis=_synthesis("first_attempt"),
        retry_synthesis=_synthesis("ollama") if retry_selected else None,
        retry_validation=SimpleNamespace(accepted=retry_accepted) if retry_selected else None,
        answer_validation=SimpleNamespace(accepted=final_accepted),
        repair_used=repaired,
        decision_dict={
            "model_generated": model_generated,
            "fallback_classification": fallback,
            "source_origin_detail": (
                "runtime_model_guided_synthesis_retry" if retry_selected
                else "runtime_model_guided_synthesis"
            ),
        },
    )


def _ledger_entry(root: Path, response: dict | None):
    return SourceOriginLedger(root).build_entry(
        turn_id="test-turn",
        trace_id="test-trace",
        user_text="Cześć",
        response_text="Wypowiedź modelu.",
        route="conversation",
        detected_intent="ordinary_dialogue",
        provenance={"response_generation_mode": "runtime_model_guided"},
        validator_result={"accepted": True},
        model_response=response,
    )


def test_first_accepted_model_response_has_correct_lineage(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("JAZN_MEMORY_MODE", "off")
    response = ResponsePipeline.selected_model_response(_state())
    entry = _ledger_entry(tmp_path, response)
    assert entry.source_origin == "model_adapter"
    assert entry.model_provider == "first_attempt"
    assert entry.model_candidate_generated is True
    assert entry.model_candidate_validated is True


def test_accepted_retry_overrides_failed_initial_candidate(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("JAZN_MEMORY_MODE", "off")
    response = ResponsePipeline.selected_model_response(_state(retry_selected=True))
    entry = _ledger_entry(tmp_path, response)
    assert entry.source_origin == "model_adapter"
    assert entry.model_provider == "ollama"
    assert entry.model_endpoint_used == "/api/chat"
    assert entry.model_candidate_generated is True
    assert entry.model_candidate_validated is True


@pytest.mark.parametrize(
    "state",
    [
        _state(retry_selected=True, retry_accepted=False),
        _state(retry_selected=True, final_accepted=False),
        _state(retry_selected=True, model_generated=False),
        _state(retry_selected=True, fallback="cannot_answer_directly"),
        _state(retry_selected=True, repaired=True),
        _state(model_generated=False),
    ],
)
def test_unselected_or_rejected_model_never_gets_credit(tmp_path: Path, monkeypatch, state) -> None:
    monkeypatch.setenv("JAZN_MEMORY_MODE", "off")
    response = ResponsePipeline.selected_model_response(state)
    assert response is None
    entry = _ledger_entry(tmp_path, response)
    assert entry.source_origin == "runtime_direct"
    assert entry.model_provider is None
    assert entry.model_candidate_generated is False
    assert entry.model_candidate_validated is False


def test_ledger_does_not_credit_non_generated_model_candidate(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("JAZN_MEMORY_MODE", "off")
    response = _synthesis("ollama", generated=False).adapter_response
    entry = _ledger_entry(tmp_path, response)
    assert entry.source_origin == "runtime_direct"
    assert entry.model_candidate_generated is False
    assert entry.model_candidate_validated is False
    assert entry.model_provider is None


def _session(tmp_path: Path, monkeypatch) -> JaznRuntimeSession:
    for name, value in {
        "JAZN_NETWORK_TIME_FIRST": "0",
        "JAZN_NETWORK_TIME_IN_TURN": "0",
        "JAZN_ALLOW_NETWORK": "0",
        "JAZN_DICTIONARY_ALLOW_NETWORK": "0",
        "JAZN_MODEL_ADAPTER": "null",
        "JAZN_LLM_ROUTE": "off",
        "JAZN_MEMORY_MODE": "off",
    }.items():
        monkeypatch.setenv(name, value)
    (tmp_path / "main.py").write_text("# isolated fixture\n", encoding="utf-8")
    return JaznRuntimeSession(
        JaznConfig(root=tmp_path),
        session_id="source-origin-regression",
        no_carryover=True,
        source_client="test",
    )


def test_successful_checkpoint_is_reported_successful(tmp_path: Path, monkeypatch) -> None:
    session = _session(tmp_path, monkeypatch)
    try:
        result = session.process_user_text("Jaka jest godzina?")
        assert result["answer_ok"] is True
        assert result["session_persistence"]["session_state_saved"] is True
        assert result["session_persistence"]["saved"] is True
        assert result["session_persistence_ok"] is True
    finally:
        session.close()


def test_explicit_checkpoint_failure_remains_failure(tmp_path: Path, monkeypatch) -> None:
    session = _session(tmp_path, monkeypatch)
    monkeypatch.setattr(
        session.state_store,
        "save",
        lambda *_args, **_kwargs: {"saved": False, "session_state_saved": True},
    )
    try:
        result = session.process_user_text("Jaka jest godzina?")
        assert result["answer_ok"] is True
        assert result["session_persistence"]["saved"] is False
        assert result["session_persistence_ok"] is False
    finally:
        session.close()
