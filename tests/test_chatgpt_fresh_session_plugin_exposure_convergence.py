from __future__ import annotations

import json
from pathlib import Path

import pytest

from latka_jazn.mcp.chatgpt_toolset import (
    REQUIRED_CHATGPT_TURN_TOOLS,
    classify_current_message_toolset,
)
from latka_jazn.mcp.chatgpt_plugin import build_portable_plugin_documents
from latka_jazn.version import PACKAGE_VERSION


ROOT = Path(__file__).resolve().parents[1]


def test_toolset_requires_current_message_observation() -> None:
    result = classify_current_message_toolset(
        REQUIRED_CHATGPT_TURN_TOOLS,
        current_message_toolset_observed=False,
    )
    assert result["full_turn_toolset_callable"] is False
    assert result["reason_code"] == "chatgpt_current_message_toolset_not_observed"


def test_toolset_rejects_incomplete_turn_surface() -> None:
    result = classify_current_message_toolset(
        ["jazn_status", "jazn_generate_visible_reply"],
        current_message_toolset_observed=True,
    )
    assert result["full_turn_toolset_callable"] is False
    assert result["missing_required_chatgpt_turn_tools"] == [
        "jazn_resume_visible_reply",
        "jazn_finalize_reply",
    ]


@pytest.mark.parametrize("bad_value", ["jazn_status", [123], [""]])
def test_toolset_input_is_fail_closed(bad_value: object) -> None:
    with pytest.raises(ValueError):
        classify_current_message_toolset(
            bad_value,
            current_message_toolset_observed=True,
        )


def test_startup_contract_publishes_fresh_message_capability_gate() -> None:
    contract = json.loads(
        (ROOT / "latka_jazn/resources/startup_contract.json").read_text(encoding="utf-8")
    )
    assert contract["chatgpt_fresh_conversation_reverification_required"] is True
    assert contract["chatgpt_current_message_toolset_observation_required"] is True
    assert contract["chatgpt_catalog_or_installed_state_sufficient"] is False
    assert contract["chatgpt_required_turn_tools"] == list(REQUIRED_CHATGPT_TURN_TOOLS)
    assert contract["chatgpt_plan_name_is_runtime_predicate"] is False
    assert contract["version"] == PACKAGE_VERSION


def test_portable_plugin_prompts_describe_current_message_validation() -> None:
    plugin = build_portable_plugin_documents("https://jazn.example.test/mcp")["plugin.json"]
    prompts = plugin["extensions"]["com.openai"]["interface"]["defaultPrompt"]
    assert any("required turn tools for this message" in value for value in prompts)
