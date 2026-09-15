from __future__ import annotations

import pytest

from latka_jazn.core.runtime_turn_contract import _prompt_cache_key_for_full_canon
from latka_jazn.model_adapters.base import ModelAdapterRequest
from latka_jazn.model_adapters.openai_responses_adapter import OpenaiResponsesAdapter


def _adapter() -> OpenaiResponsesAdapter:
    return OpenaiResponsesAdapter(api_key="test-key", model="gpt-test")


def _function_tool(name: str) -> dict:
    return {
        "type": "function",
        "name": name,
        "description": f"test tool {name}",
        "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        "strict": True,
    }


def test_prompt_cache_key_is_derived_only_from_immutable_canon_hash() -> None:
    digest = "a" * 64
    key = _prompt_cache_key_for_full_canon({"immutable_canon_sha256": digest})
    assert key == "jazn-canon-" + "a" * 48
    assert len(key) <= 64
    assert _prompt_cache_key_for_full_canon({"immutable_canon_sha256": "not-a-hash"}) is None


def test_responses_payload_keeps_stable_canon_before_dynamic_turn_and_user_text_last() -> None:
    request = ModelAdapterRequest(
        prompt="dynamic user message",
        system_context={
            "full_canon_model_context": {"immutable_canon_sha256": "a" * 64, "read_only": True},
            "turn_id": "turn-dynamic",
            "route": "ordinary_dialogue",
        },
        prompt_cache_key="jazn-canon-" + "a" * 48,
    )
    payload = _adapter()._build_payload(request)
    input_text = str(payload["input"])

    stable_at = input_text.index("STABILNY_KANON_JAZNI_JSON:")
    dynamic_at = input_text.index("DYNAMICZNY_KONTEKST_TURY_JSON:")
    user_at = input_text.index("AKTUALNA_WIADOMOSC_UZYTKOWNIKA:")
    assert stable_at < dynamic_at < user_at
    assert input_text.endswith("dynamic user message")
    assert payload["prompt_cache_key"] == "jazn-canon-" + "a" * 48


def test_prompt_cache_key_rejects_unbounded_or_user_shaped_value() -> None:
    request = ModelAdapterRequest(
        prompt="hello",
        prompt_cache_key="user@example.com/" + "x" * 80,
    )
    with pytest.raises(ValueError, match="prompt_cache_key_invalid"):
        _adapter()._build_payload(request)


def test_allowed_tools_restricts_declared_tool_universe_without_removing_definitions() -> None:
    weather = _function_tool("get_weather")
    search = _function_tool("search_docs")
    delete = _function_tool("delete_record")
    request = ModelAdapterRequest(
        prompt="find the docs",
        tools=[weather, search, delete],
        allowed_tool_names=["search_docs"],
    )
    payload = _adapter()._build_payload(request)

    assert payload["tools"] == [weather, search, delete]
    assert payload["tool_choice"] == {
        "type": "allowed_tools",
        "mode": "auto",
        "tools": [{"type": "function", "name": "search_docs"}],
    }


def test_allowed_tools_can_require_one_of_runtime_authorized_subset() -> None:
    request = ModelAdapterRequest(
        prompt="must use one tool",
        tools=[_function_tool("lookup_a"), _function_tool("lookup_b")],
        allowed_tool_names=["lookup_b"],
        tool_choice="required",
    )
    payload = _adapter()._build_payload(request)
    assert payload["tool_choice"]["mode"] == "required"
    assert payload["tool_choice"]["tools"] == [{"type": "function", "name": "lookup_b"}]


def test_unknown_runtime_allowed_tool_fails_closed() -> None:
    request = ModelAdapterRequest(
        prompt="hello",
        tools=[_function_tool("safe_lookup")],
        allowed_tool_names=["not_declared"],
    )
    with pytest.raises(ValueError, match="allowed_tool_not_declared:not_declared"):
        _adapter()._build_payload(request)


def test_allowed_tools_cannot_be_combined_with_independent_explicit_choice() -> None:
    request = ModelAdapterRequest(
        prompt="hello",
        tools=[_function_tool("safe_lookup")],
        allowed_tool_names=["safe_lookup"],
        tool_choice={"type": "function", "name": "safe_lookup"},
    )
    with pytest.raises(ValueError, match="allowed_tools_conflict_with_explicit_tool_choice"):
        _adapter()._build_payload(request)


def test_allowed_tools_without_declared_tools_fails_closed() -> None:
    request = ModelAdapterRequest(prompt="hello", allowed_tool_names=["safe_lookup"])
    with pytest.raises(ValueError, match="allowed_tool_names_require_declared_tools"):
        _adapter()._build_payload(request)
