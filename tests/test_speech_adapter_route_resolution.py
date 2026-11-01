"""One route decision per speech build; no hidden local or paid execution."""
import pytest

from latka_jazn.config import JaznConfig
from latka_jazn.core import llm_route_resolver as routes
from latka_jazn.core.model_guided_speech_runtime import (
    build_model_guided_speech_status, build_speech_adapter_for_turn,
)
from latka_jazn.model_adapters import factory
from latka_jazn.model_adapters.null_model_adapter import NullModelAdapter


@pytest.fixture
def config(tmp_path, monkeypatch):
    for key, value in {"JAZN_MODEL_ADAPTER":"null", "JAZN_LLM_ROUTE":"auto",
                       "JAZN_ASSUME_CHATGPT_HOST":"0", "JAZN_ALLOW_PAID_OPENAI":"0",
                       "JAZN_MODEL_GUIDED_SPEECH":"1", "JAZN_LLM_ROUTE_SKIP_LOCAL_PROBE":"0"}.items():
        monkeypatch.setenv(key,value)
    return JaznConfig(root=tmp_path, model_adapter="null", llm_route_mode="auto",
                      local_model_name="", allow_network=False)


@pytest.mark.parametrize("builder", ["turn", "status"])
def test_no_probe_contract_reaches_adapter_construction(config, monkeypatch, builder):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("No-probe construction attempted local discovery")
    monkeypatch.setattr(routes, "probe_ollama", forbidden)
    if builder == "turn":
        adapter, status = build_speech_adapter_for_turn(config, probe_local=False)
        assert isinstance(adapter, NullModelAdapter)
    else:
        status = build_model_guided_speech_status(config, probe_local=False)
    assert status.selected_route == routes.ROUTE_NULL
    assert status.can_generate_model_guided_speech is False
    assert status.paid_route is False
    assert config.model_adapter == "null"


@pytest.mark.parametrize("builder", ["speech", "legacy_factory"])
def test_requested_discovery_runs_once_and_default_factory_remains_compatible(config, monkeypatch, builder):
    probes = []
    def unavailable(*_args, **_kwargs):
        probes.append(1)
        return {"available":False, "model":"", "reason":"synthetic_unavailable"}
    monkeypatch.setattr(routes, "probe_ollama", unavailable)
    if builder == "speech":
        adapter, status = build_speech_adapter_for_turn(config, probe_local=True)
        assert status.selected_route == routes.ROUTE_NULL
    else:
        adapter = factory.build_model_adapter(config)
    assert isinstance(adapter, NullModelAdapter)
    assert probes == [1]
