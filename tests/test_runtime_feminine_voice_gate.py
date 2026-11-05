"""Pre-acceptance voice validation preserves quotations and rejects own male voice."""
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

from latka_jazn.core.runtime_answer_validator import RuntimeAnswerValidator
from latka_jazn.core.finalization_service import FinalizationService
from latka_jazn.core.host_regeneration_policy import decide_host_regeneration
import latka_jazn.core.host_finalization_transaction as tx


def validate(text, intent="ordinary_conversation", route="ordinary_dialogue"):
    return RuntimeAnswerValidator().validate_model_candidate(
        user_text="Potwierdź odbiór kodu TPAEEB0D927.",
        response={"status": "completed", "text": text},
        route=route, detected_intent=intent,
    )


@pytest.mark.parametrize("text", [
    "Powinienem sprawdzić kod.", "Jestem gotowy.",
    "Zapamiętałem. TPAEEB0D927.", "Sprawdziłem kod.", "Byłem tutaj.",
    "Chciałbym pomóc.", "Mogłem to odczytać.", "Zapamietalem kod.",
    "Jestem Łatką. Zrobiłem to.", 'Cytat: „Zrobiłam to”. Zapamiętałem kod.',
    '„Zapamiętałem kod.',
])
def test_masculine_narration_is_rejected_before_acceptance(text):
    result = validate(text)
    assert not result.accepted and not result.can_show_to_user
    assert result.must_regenerate
    assert result.mismatch_reason == "voice_perspective_mismatch"
    assert result.required_repair_route == "first_person_feminine_voice_repair"


@pytest.mark.parametrize("text", [
    "Zapamiętałam. TPAEEB0D927.", "Sprawdziłam kod.", "Chciałabym pomóc.",
    'Przytoczyłam słowa użytkownika: „Zapamiętałem kod”.',
    'W logu zapisano: "Zapamiętałem. TPAEEB0D927."',
    "Przytaczam:\n> Zapamiętałem kod.\nPotwierdziłam odbiór.",
    "Przykład: `Zapamiętałem`. Potwierdziłam odbiór.",
    "Przytoczyłam: 'Zapamiętałem'.",
    "To problem z modelem i plikiem.",
    "Źródłem jest zapis przekazany kanałem transportowym.",
    "Nad stołem, pod kołem i za czołem. Z materiałem i popiołem.",
])
def test_feminine_narration_and_quoted_source_are_preserved(text):
    result = validate(text)
    assert result.accepted, result.to_dict()
    assert result.repair_body is None


def test_dedicated_handler_or_technical_route_cannot_bypass_masculine_gate():
    assert validate("Zapamiętałem kod.", "runtime_health_check", "runtime_health").mismatch_reason == "voice_perspective_mismatch"
    assert not RuntimeAnswerValidator()._voice_perspective_mismatch(
        "Raport: Łatka jest dostępna.", "system_diagnostic_question", "diagnostic")


def test_voice_rejection_has_one_retry_and_preserves_other_integrity_gates():
    assert decide_host_regeneration(["voice_perspective_mismatch"], attempts_used=0).regenerate
    assert not decide_host_regeneration(["voice_perspective_mismatch"], attempts_used=1).regenerate
    assert not decide_host_regeneration(["voice_perspective_mismatch", "full_canon_context_missing_or_invalid"], attempts_used=0).regenerate


@pytest.mark.parametrize("attempts", [0, 1])
def test_real_voice_validator_rejection_never_reaches_finalizer(monkeypatch, attempts):
    binding = {"turn_id": "voice-turn", "trace_id": "voice-trace"}
    reply = {**binding, "host_request_contract_hash": "request-hash", "final_text": "Zapamiętałem. TPAEEB0D927."}
    original = dict(reply)
    pending = {"binding": binding, "generation_context": {"host_generation_context": {}},
               "regeneration_attempts": attempts, "max_regeneration_attempts": 1}
    monkeypatch.setattr(tx, "claim_pending_host_request", lambda *args, **kwargs: pending)
    def evaluate(**kwargs):
        result = validate(kwargs["final_text"])
        return {"accepted": result.accepted, "violations": [result.mismatch_reason], "runtime_validation": result.to_dict()}
    monkeypatch.setattr(tx, "evaluate_host_response_candidate", evaluate)
    monkeypatch.setattr(tx, "finalize_host_visible_text", lambda **kwargs: pytest.fail("rejected voice reached finalizer"))
    retries, releases = [], []
    def retry(*args, **kwargs):
        retries.append(kwargs)
        return {**pending, "regeneration_attempts": 1, "request_contract_hash": "request-hash"}
    monkeypatch.setattr(tx, "request_host_regeneration", retry)
    monkeypatch.setattr(tx, "release_claimed_host_request", lambda *args, **kwargs: releases.append(kwargs))
    ports = tx.HostFinalizationPorts(
        extract_payload=lambda _: (reply, []), presentation=lambda _: {"action": "generate_then_finalize"},
        commit_conversation=lambda **kwargs: pytest.fail("rejected voice persisted"),
        commit_session=lambda **kwargs: pytest.fail("rejected voice persisted"))
    service = cast(FinalizationService, SimpleNamespace(config=SimpleNamespace(root=Path("/unused")), transition=lambda _: None))
    result, errors = tx.finalize_host_candidate(service=service, ports=ports, payload={}, chat_bridge_meta={}, contract={})
    assert reply == original  # No post-acceptance text correction.
    if attempts == 0:
        assert not errors and result is not None and len(retries) == 1
        bridge = result["chatgpt_host_bridge"]
        assert bridge["turn_id"] == binding["turn_id"]
        assert bridge["regeneration_violations"] == ["voice_perspective_mismatch"]
        assert bridge["repair_guidance"]
    else:
        assert result is None and not retries and len(releases) == 1
        assert "host_regeneration:host_regeneration_budget_exhausted" in errors
