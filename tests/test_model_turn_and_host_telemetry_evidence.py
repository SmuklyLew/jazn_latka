"""Evidence is tied to concrete events; never infer it from adapter config."""
from __future__ import annotations

from latka_jazn.core.telemetry_evidence import memory_observation
from latka_jazn.model_adapters.base import ModelAdapterRequest, ModelAdapterResponse
from latka_jazn.model_adapters.turn_evidence import model_turn_evidence


def test_adapter_status_is_not_a_completed_model_generation() -> None:
    req = ModelAdapterRequest(prompt="test", metadata={"turn_id": "t1", "trace_id": "trace1"})
    response = ModelAdapterResponse(
        text="", provider="ollama", model="gemma3:latest",
        status="not_probed", adapter_id="local_llm_adapter", endpoint_used=None,
    )
    info = model_turn_evidence(req, response)
    assert info["generation_observed"] is False
    assert info["model_identity_verified_from_provider"] is False
    assert info["evidence_origin"] == "not_verified"


def test_completed_adapter_response_retains_turn_lineage_and_real_model() -> None:
    req = ModelAdapterRequest(prompt="test", metadata={"turn_id": "t42", "trace_id": "x42"})
    response = ModelAdapterResponse(
        text="OK", provider="ollama", model="gemma3:latest",
        status="completed", adapter_id="local_llm_adapter",
        endpoint_used="/api/chat",
        transport={"attempts": [{"actual_model": "gemma3:latest", "actual_model_source": "provider_response"}]},
    )
    info = model_turn_evidence(req, response)
    assert info["lineage_verified"] is True
    assert info["generation_observed"] is True
    assert info["model_identity_verified_from_provider"] is True
    assert info["turn_id"] == "t42"
    assert info["trace_id"] == "x42"


def test_configured_model_fallback_never_passes_as_provider_identity() -> None:
    req = ModelAdapterRequest(prompt="test", metadata={"turn_id": "t45", "trace_id": "x45"})
    response = ModelAdapterResponse(
        text="OK", provider="ollama", model="gemma3:latest",
        status="completed", endpoint_used="/api/chat",
        transport={"attempts": [
            {"actual_model": "gemma3:latest", "actual_model_source": "configured_fallback"},
        ]},
    )
    evidence = model_turn_evidence(req, response)
    assert evidence["generation_observed"] is True
    assert evidence["model_identity_verified_from_provider"] is False
    assert evidence["transport_observed_model"] is None
    assert evidence["model_name_origin"] == "configured_fallback"


def test_configured_model_label_alone_is_never_transport_verified() -> None:
    req = ModelAdapterRequest(prompt="test")
    response = ModelAdapterResponse(
        text="OK", provider="ollama", model="gemma3:latest",
        status="completed", endpoint_used="/api/chat",
    )
    info = model_turn_evidence(req, response)
    assert info["generation_observed"] is True
    assert info["model_identity_verified_from_provider"] is False
    assert info["transport_observed_model"] is None
    assert info["lineage_verified"] is False


def test_ram_telemetry_without_trusted_os_measurement_is_unknown() -> None:
    for value in [
        memory_observation(None, None, source=None),
        memory_observation(100, 50, source="model_statement"),
        memory_observation(100, 150, source="windows_globalmemorystatusex"),
        memory_observation(0, 0, source="linux_proc_meminfo"),
        memory_observation(True, 0, source="linux_proc_meminfo"),
    ]:
        assert value["status"] == "not_verified"
        assert value["physical_ram_percent_used"] is None


def test_ram_percentage_retains_os_origin_and_timestamp() -> None:
    evidence = memory_observation(1000, 542, source="windows_globalmemorystatusex")
    assert evidence["status"] == "observed"
    assert evidence["physical_ram_percent_used"] == 45.8
    assert evidence["observed_at_utc"].endswith("+00:00")
    assert evidence["source"] == "windows_globalmemorystatusex"
