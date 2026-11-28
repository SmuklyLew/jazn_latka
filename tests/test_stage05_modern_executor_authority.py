"""Modern generation need cannot manufacture host authorization."""
from typing import Any

import pytest

from latka_jazn.core.model_executor_preflight import host_generation_requested
from latka_jazn.core.conversation_runner import _host_finalization_pending
from latka_jazn.core.chat_command_contract import chatgpt_result_requires_host_visible_reply


@pytest.mark.parametrize("executor", [None, {}, {"executor": "host_bridge"},
    {"executor": "host_bridge", "available": False},
    {"executor": "local_model", "available": True},
    {"executor": "external_model", "available": True},
    {"executor": "unavailable", "available": False}])
def test_modern_generation_need_does_not_authorize_host(executor: dict[str, Any] | None) -> None:
    decision: dict[str, Any] = {"model_generation_required": True, "requires_host_model": True}
    if executor is not None:
        decision["model_executor_preflight"] = executor
    result = {
        "conversation_decision": decision,
        "final_response_contract": {"requires_host_model": True},
    }
    assert host_generation_requested(result) is False
    assert _host_finalization_pending(result, can_continue=True) == (False, [])
    assert chatgpt_result_requires_host_visible_reply(result) is False


def test_modern_explicit_host_executor_is_eligible_for_existing_contract_gate() -> None:
    result: dict[str, Any] = {"conversation_decision": {
        "model_generation_required": True,
        "requires_host_model": True,
        "model_executor_preflight": {"executor": "host_bridge", "available": True},
    }}
    assert host_generation_requested(result) is True
    # Authorization of the selected executor does not make an incomplete
    # phase-1 request valid, nor does it mean finalization was accepted.
    pending, missing = _host_finalization_pending(result, can_continue=True)
    assert pending is False
    assert missing
