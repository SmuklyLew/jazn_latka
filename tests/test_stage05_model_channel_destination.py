"""Client model channels must not redirect operator credentials or remove timeout bounds."""
from pathlib import Path

import pytest

from latka_jazn.config import JaznConfig
from latka_jazn.core.conversation_channel import (
    apply_model_channel_config,
    model_channel_config_from_config,
    normalize_model_channel_config,
)


@pytest.mark.parametrize("endpoint", [
    "https://unapproved.invalid/v1",
    "http://127.0.0.1:9999/v1",
    "https://api.openai.com.unapproved.invalid/v1",
    "",
])
def test_client_cannot_redirect_operator_api_destination(tmp_path: Path, endpoint: str) -> None:
    config = JaznConfig(root=tmp_path, model_api_base="https://api.openai.com/v1",
                        allow_paid_openai_api=True)
    with pytest.raises(ValueError, match="model_channel_external_endpoint_override_forbidden"):
        apply_model_channel_config(config, {"model_api_base": endpoint, "model_adapter": "openai"})
    assert config.model_api_base == "https://api.openai.com/v1"


def test_operator_configured_destination_survives_channel_projection(tmp_path: Path) -> None:
    config = JaznConfig(root=tmp_path, model_api_base="https://operator-configured.invalid/v1",
                        allow_paid_openai_api=True)
    channel = model_channel_config_from_config(config)
    routed = apply_model_channel_config(config, channel)
    assert routed.model_api_base == config.model_api_base
    assert routed is not config
    assert apply_model_channel_config(config, {"model_api_base": config.model_api_base + "/"}).model_api_base == config.model_api_base


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf"), "NaN", "Infinity", 0.0, -1.0])
def test_unbounded_model_timeout_is_rejected(value: object) -> None:
    with pytest.raises(ValueError, match="model_channel_config_positive_required:model_timeout_seconds"):
        normalize_model_channel_config({"model_timeout_seconds": value})


def test_positive_finite_timeout_preserved() -> None:
    assert normalize_model_channel_config({"model_timeout_seconds": 120.0}) == {"model_timeout_seconds": 120.0}
