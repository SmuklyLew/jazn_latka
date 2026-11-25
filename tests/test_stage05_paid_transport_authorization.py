"""Paid inference cannot bypass authorization through direct transport or a turn override."""
from pathlib import Path

import pytest

from latka_jazn.config import JaznConfig
from latka_jazn.core.conversation_channel import apply_model_channel_config, model_channel_config_from_config
from latka_jazn.core.llm_route_resolver import paid_openai_allowed
from latka_jazn.model_adapters.base import ModelAdapterRequest
from latka_jazn.model_adapters import factory
from latka_jazn.model_adapters.openai_responses_adapter import OpenaiResponsesAdapter


def test_turn_denial_remains_denied_despite_operator_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JAZN_ALLOW_PAID_OPENAI", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-not-sent")
    cfg = JaznConfig(root=tmp_path, model_adapter="openai", model_name="synthetic", allow_network=True)
    routed = apply_model_channel_config(cfg, {"allow_paid_openai_api": False})
    assert paid_openai_allowed(cfg, {"JAZN_ALLOW_PAID_OPENAI": "1"})
    assert not paid_openai_allowed(routed, {"JAZN_ALLOW_PAID_OPENAI": "1"})
    assert "paid_openai_turn_denied" not in model_channel_config_from_config(routed)
    narrowed_again = apply_model_channel_config(routed, {"allow_paid_openai_api": True})
    assert not paid_openai_allowed(narrowed_again, {"JAZN_ALLOW_PAID_OPENAI": "1"})
    monkeypatch.setattr(factory, "OpenaiResponsesAdapter", lambda **_k: pytest.fail("paid adapter constructed"))
    assert factory.build_model_adapter(routed, resolve_route=False).describe()["failure_reason"] == "paid_openai_not_allowed"


@pytest.mark.parametrize(("opt_in", "network", "endpoint", "reason"), [
    (False, True, "https://api.openai.com/v1", "paid_openai_not_allowed"),
    (True, False, "https://api.openai.com/v1", "openai_network_permission_missing"),
    (True, True, "http://127.0.0.1:1234/v1", "openai_endpoint_not_authorized"),
    (True, True, "https://user@api.openai.com/v1", "openai_endpoint_not_authorized"),
    (True, True, "https://api.openai.com/v1?other=1", "openai_endpoint_not_authorized"),
    (True, True, "https://api.openai.com/v1#fragment", "openai_endpoint_not_authorized"),
])
def test_direct_adapter_refuses_before_transport(
    opt_in: bool, network: bool, endpoint: str, reason: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = OpenaiResponsesAdapter(api_key="synthetic-not-sent", model="synthetic",
                                    api_base=endpoint, operator_opt_in=opt_in, network_permitted=network)
    monkeypatch.setattr(adapter, "_post_json", lambda _p: pytest.fail("unauthorized transport"))
    assert adapter.generate(ModelAdapterRequest(prompt="synthetic")).status == reason
    assert adapter.describe()["failure_reason"] == reason
    assert not adapter.describe()["can_attempt_model_guided_speech"]
    with pytest.raises(PermissionError, match=reason):
        adapter._post_json_windows({})


def test_explicit_network_denial_is_not_paid_opt_in(tmp_path: Path) -> None:
    cfg = JaznConfig(root=tmp_path, allow_network=False, allow_paid_openai_api=True)
    assert not paid_openai_allowed(cfg, {"JAZN_ALLOW_PAID_OPENAI": "1"})
