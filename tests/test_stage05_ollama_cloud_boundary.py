"""Stage 05: reject known Ollama cloud models and remote aliases before inference."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from latka_jazn.config import JaznConfig
from latka_jazn.core import llm_route_resolver as router
from latka_jazn.model_adapters import local_llm_adapter as native
from latka_jazn.model_adapters import openai_compatible_local_adapter as compatible
from latka_jazn.model_adapters.base import ModelAdapterRequest


@pytest.mark.parametrize("name", ["gpt-oss:120b-cloud", "gemma4:cloud", "some/model-cloud"])
def test_cloud_selector_cannot_reach_either_ollama_adapter(
    name: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(*_a: Any, **_k: Any) -> Any:
        pytest.fail("cloud model must not receive a request")
    monkeypatch.setattr(native, "urlopen", fail)
    monkeypatch.setattr(compatible, "urlopen", fail)
    request = ModelAdapterRequest(prompt="synthetic")
    a = native.LocalLlmAdapter(model=name)
    b = compatible.OpenAICompatibleLocalAdapter(provider="ollama", model=name)
    assert a.generate(request).status == "ollama_cloud_model_not_authorized"
    assert b.generate(request).status == "ollama_cloud_model_not_authorized"
    assert not a.probe()["probe_ok"]
    assert b.probe().last_probe_error == "ollama_cloud_model_not_authorized"


@pytest.mark.parametrize("remote_field", ["remote_model", "remote_host"])
def test_remote_metadata_excludes_alias_even_if_running(
    remote_field: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake(url: str, *, timeout_seconds: float) -> dict[str, Any]:
        if url.endswith("/api/ps"):
            return {"models": [{"name": "alias:latest"}]}
        return {"models": [{"name": "alias:latest", remote_field: "upstream"},
                           {"name": "local:latest"}]}
    monkeypatch.setattr(router, "_http_json", fake)
    cfg = JaznConfig(root=tmp_path, local_model_name="alias:latest")
    result = router.probe_ollama(cfg, {})
    assert result["available"] is False
    assert result["reason"] == "ollama_cloud_model_not_authorized"
    assert result["running_models"] == []
    assert result["installed_models"] == ["local:latest"]
    cfg.local_model_name = ""
    automatic = router.probe_ollama(cfg, {})
    assert automatic["available"] is True
    assert automatic["model"] == "local:latest"


def test_automatic_ollama_discovery_uses_local_egress_policy(tmp_path: Path) -> None:
    cfg = JaznConfig(root=tmp_path, local_model_api_base="https://example.invalid",
                     local_model_name="synthetic")
    result = router.probe_ollama(cfg, {})
    assert result["available"] is False
    assert result["endpoint_reachable"] is False
    assert result["errors"] == ["/api/ps:unavailable", "/api/tags:unavailable"]
