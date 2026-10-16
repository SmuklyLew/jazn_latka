from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from latka_jazn.model_adapters.base import ModelAdapterRequest
from latka_jazn.model_adapters.factory import build_model_adapter
from latka_jazn.model_adapters.siwc_plan_usage_adapter import (
    SIWC_REQUIRED_SCOPE,
    SIWC_RESPONSES_URL,
    SiwcPlanUsageAdapter,
    _DenyRedirect,
    _sse_events,
)

_FORBIDDEN = {
    "background", "conversation", "max_output_tokens", "max_tool_calls",
    "metadata", "moderation", "multi_agent", "prompt",
    "prompt_cache_retention", "safety_identifier", "temperature",
    "top_logprobs", "top_p", "truncation", "user", "previous_response_id",
}


def _adapter(events, *, opt_in=True, scopes=SIWC_REQUIRED_SCOPE, network=True):
    requests = []

    def transport(payload, token, timeout):
        requests.append((payload, token, timeout))
        return iter(events)

    return (
        SiwcPlanUsageAdapter(
            model="model-from-account-catalog",
            access_token="secret-never-print",
            granted_scopes=scopes,
            operator_opt_in=opt_in,
            network_permitted=network,
            stream_transport=transport,
        ),
        requests,
    )


def _complete(text="Cześć"):
    return {
        "type": "response.completed",
        "response": {
            "status": "completed",
            "model": "model-from-account-catalog",
            "output": [{
                "type": "message",
                "content": [{"type": "output_text", "text": text}],
            }],
        },
    }


def test_siwc_never_sends_preview_forbidden_fields():
    adapter, sent = _adapter([_complete()])
    result = adapter.generate(ModelAdapterRequest(
        prompt="Powiedz cześć",
        system_context={"previous_turns": ["hej", "cześć"]},
        metadata={"not_for_wire": "private"},
        max_output_tokens=320,
        prompt_cache_key="not-supported",
    ))
    assert result.status == "completed"
    assert result.text == "Cześć"
    assert result.provider == "openai_siwc"
    assert result.requires_runtime_authorization is False
    payload, token, _ = sent[0]
    assert payload["store"] is False
    assert payload["stream"] is True
    assert payload["input"][0]["role"] == "user"
    assert isinstance(payload["input"], list)
    assert "previous_turns" in payload["input"][0]["content"]
    assert set(payload).isdisjoint(_FORBIDDEN)
    assert token == "secret-never-print"
    assert "secret-never-print" not in json.dumps(adapter.describe())
    assert "secret-never-print" not in json.dumps(result.to_dict())
    assert SIWC_RESPONSES_URL == "https://api.openai.com/v1/responses"


@pytest.mark.parametrize("events,expected", [
    ([{"type": "response.output_text.delta", "delta": "partial"}], "siwc_stream_missing_completion"),
    ([{"type": "response.output_text.delta", "delta": "partial"},
      {"type": "response.failed", "response": {"error": {"code": "subscription_sharing_usage_limit_exceeded"}}}],
     "siwc_response_not_completed"),
    ([{"type": "response.incomplete"}], "siwc_response_not_completed"),
    ([{"type": "response.completed", "response": {"status": "failed", "output": []}}],
     "siwc_stream_transport_error"),
])
def test_siwc_never_exposes_partial_or_failed_completion(events, expected):
    adapter, sent = _adapter(events)
    result = adapter.generate(ModelAdapterRequest(prompt="Hi"))
    assert len(sent) == 1
    assert result.status == expected
    assert result.text == ""
    assert result.generated is False
    assert result.validated is False


@pytest.mark.parametrize("option,reason", [
    ({"opt_in": False}, "siwc_explicit_opt_in_required"),
    ({"scopes": "openid profile email"}, "siwc_plan_scope_missing"),
    ({"network": False}, "siwc_network_permission_missing"),
])
def test_siwc_fail_closed_before_network(option, reason):
    adapter, sent = _adapter([_complete()], **option)
    result = adapter.generate(ModelAdapterRequest(prompt="Hi"))
    assert result.status == reason
    assert sent == []
    assert adapter.describe()["configured"] is False


def test_siwc_requires_separately_selected_model_and_token():
    for kwargs in ({"model": ""}, {"model": "../../bad"}, {"access_token": ""}):
        values = {
            "model": "catalog-model",
            "access_token": "token",
            "granted_scopes": SIWC_REQUIRED_SCOPE,
            "operator_opt_in": True,
        }
        values.update(kwargs)
        adapter = SiwcPlanUsageAdapter(**values)
        assert adapter.describe()["configured"] is False


def test_siwc_disallows_previous_response_and_tool_dispatch():
    adapter, sent = _adapter([_complete()])
    for request in (
        ModelAdapterRequest(prompt="Hi", previous_response_id="resp_secret"),
        ModelAdapterRequest(prompt="Hi", tools=[{"type": "function", "name": "execute_anything"}]),
        ModelAdapterRequest(prompt="Hi", response_schema={"type": "object"}),
    ):
        result = adapter.generate(request)
        assert result.status == "siwc_request_unsupported"
        assert result.text == ""
    assert sent == []


def test_siwc_sse_parser_needs_complete_json_events():
    payload = json.dumps({"type": "response.output_text.delta", "delta": "hej"}).encode("utf-8")
    raw = [b": keep-alive\n", b"data: " + payload + b"\n", b"\n", b"data: [DONE]\n", b"\n"]
    assert list(_sse_events(raw)) == [{"type": "response.output_text.delta", "delta": "hej"}]
    with pytest.raises(ValueError, match="siwc_non_object_event"):
        list(_sse_events([b"data: []\n", b"\n"]))


def test_siwc_factory_does_not_auto_enable(monkeypatch):
    cfg = SimpleNamespace(model_adapter="siwc", allow_network=True, model_timeout_seconds=4)
    monkeypatch.delenv("JAZN_SIWC_OPERATOR_OPT_IN", raising=False)
    monkeypatch.setenv("JAZN_SIWC_ACCESS_TOKEN", "secret")
    monkeypatch.setenv("JAZN_SIWC_GRANTED_SCOPES", SIWC_REQUIRED_SCOPE)
    monkeypatch.setenv("JAZN_SIWC_MODEL", "catalog-model")
    adapter = build_model_adapter(cfg)
    assert isinstance(adapter, SiwcPlanUsageAdapter)
    assert adapter.describe()["configured"] is False
    monkeypatch.setenv("JAZN_SIWC_OPERATOR_OPT_IN", "1")
    assert build_model_adapter(cfg).describe()["configured"] is True
    cfg.model_adapter = "null"
    monkeypatch.delenv("JAZN_MODEL_ADAPTER", raising=False)
    assert not isinstance(build_model_adapter(cfg), SiwcPlanUsageAdapter)


def test_siwc_http_redirect_is_rejected_to_protect_bearer():
    assert _DenyRedirect().redirect_request(
        None, None, 302, "redirect", {}, "https://other.example/capture"
    ) is None


def test_siwc_invalid_event_does_not_count_as_completion():
    adapter, called = _adapter(["invalid-frame", _complete()])
    result = adapter.generate(ModelAdapterRequest(prompt="Hi"))
    assert called
    assert result.status == "siwc_stream_transport_error"
    assert result.text == ""
    assert adapter.describe()["can_generate_model_guided_speech"] is False


def test_siwc_previous_success_cannot_leak_into_failed_request():
    adapter, _ = _adapter([_complete()])
    assert adapter.generate(ModelAdapterRequest(prompt="Hi")).status == "completed"
    result = adapter.generate(ModelAdapterRequest(prompt="Hi", previous_response_id="resp_123"))
    assert result.status == "siwc_request_unsupported"
    assert result.status_snapshot is not None
    assert result.status_snapshot.can_generate_model_guided_speech is False
