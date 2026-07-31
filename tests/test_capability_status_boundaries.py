from __future__ import annotations

from typing import Any

from latka_jazn.core.handlers.capability_status_handler import CapabilityStatusHandler


def test_model_adapter_status_rejects_a_non_object_nested_contract() -> None:
    adapter: dict[str, Any] = {
        "provider": "ollama",
        "model": "gemma3",
        "adapter_contract": ["invalid", "shape"],
    }

    result = CapabilityStatusHandler().handle(
        "Jaki jest status modelu?",
        {
            "intent": "model_adapter_status_question",
            "model_adapter_status": adapter,
        },
    )

    assert result.route == "model_adapter_status"
    assert "provider=ollama" in result.body
    assert "model=gemma3" in result.body
    assert "adapter=not_configured" in result.body


def test_capability_status_uses_a_non_shadowed_version_parser() -> None:
    result = CapabilityStatusHandler().handle(
        "Co potrafisz?",
        {"intent": "capability_status_question"},
    )

    assert result.route == "capability_status"
    assert result.source_origin_detail.startswith("capability_status_handler/v")
