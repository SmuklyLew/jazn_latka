"""Factory opt-in must not be bypassed by explicit adapter or disabled re-routing."""
from pathlib import Path
import pytest

from latka_jazn.config import JaznConfig
from latka_jazn.model_adapters import factory


@pytest.mark.parametrize("resolve_route", [False, True])
@pytest.mark.parametrize("name", ["openai", "openai_responses", "openai_responses_adapter"])
def test_explicit_paid_adapter_denied_without_opt_in(tmp_path: Path, monkeypatch, resolve_route: bool, name: str) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-not-a-key")
    monkeypatch.setenv("JAZN_ALLOW_PAID_OPENAI", "0")
    monkeypatch.setattr(factory, "OpenaiResponsesAdapter", lambda **_k: pytest.fail("unauthorized paid adapter constructed"))
    cfg = JaznConfig(root=tmp_path, model_adapter=name, model_name="synthetic", allow_network=True, allow_paid_openai_api=True)
    adapter = factory.build_model_adapter(cfg, resolve_route=resolve_route)
    assert adapter.describe()["failure_reason"] == "paid_openai_not_allowed"
    assert not adapter.describe()["can_attempt_model_guided_speech"]


def test_paid_adapter_explicit_opt_in_allows_construction_only(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-not-a-key")
    monkeypatch.setenv("JAZN_ALLOW_PAID_OPENAI", "1")
    cfg = JaznConfig(root=tmp_path, model_adapter="openai", model_name="synthetic", allow_network=True)
    adapter = factory.build_model_adapter(cfg, resolve_route=False)
    assert isinstance(adapter, factory.OpenaiResponsesAdapter)
    assert not adapter.describe()["can_generate_model_guided_speech"]
