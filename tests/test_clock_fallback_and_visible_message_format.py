from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from latka_jazn.core.clock import TimeSample, TimeSourceResolver, WarsawClock
from latka_jazn.core.final_response_contract import FinalResponseContract
from latka_jazn.core.host_visible_finalization import finalize_host_visible_text
from latka_jazn.core.message_envelope import MessageEnvelope
from latka_jazn.core.runtime_truth_gate import apply_runtime_truth_gate
from latka_jazn.core.visible_integrity import validate_result_integrity
from latka_jazn.core.visible_message_format import (
    CLOCK_UNAVAILABLE_HEADER,
    render_clock_header,
    render_visible_message,
)
from latka_jazn.version import PACKAGE_VERSION

BODY = "Działam bez zależności od zegara."
AUTHOR = "Łatka"
MARKER = "🌿"


def _unavailable_decision() -> dict[str, Any]:
    visible = render_visible_message(
        clock_header=CLOCK_UNAVAILABLE_HEADER,
        state_emoticon=MARKER,
        author_label=AUTHOR,
        body=BODY,
    )
    return {
        "fallback_classification": "rule_handler_response",
        "route": "presence",
        "handler_name": "presence_handler",
        "handler_result": {
            "handler_name": "presence_handler",
            "body": BODY,
            "required_components": ["presence"],
            "satisfied_components": ["presence"],
            "missing_components": [],
        },
        "final_answer_validation": {"accepted": True, "must_regenerate": False},
        "template_origin": {},
        "runtime_provenance": {
            "handler_name": "presence_handler",
            "source_origin_detail": "presence_handler",
            "response_generation_mode": "runtime_dynamic",
            "exact_runtime_text": BODY,
            "runtime_text_hash": hashlib.sha256(BODY.encode()).hexdigest(),
            "visible_answer_text": visible,
            "visible_answer_hash": hashlib.sha256(visible.encode()).hexdigest(),
        },
        "timestamp_contract": {
            "clock_available": False,
            "trusted": False,
            "source": "unavailable",
            "sample_iso": None,
            "timezone": "Europe/Warsaw",
            "require_trusted_in_final_visible": False,
            "allow_degraded_local_visible": True,
        },
        "author_id": "latka_runtime",
        "author_label": AUTHOR,
        "author_source": "jazn_runtime",
        "voice_source_contract": {
            "speaking_identity": AUTHOR,
            "active_source": "jazn_runtime",
        },
    }


def test_canonical_clock_header_has_brackets_and_minute_precision() -> None:
    local_dt = datetime(2026, 8, 4, 0, 4, 59, tzinfo=ZoneInfo("Europe/Warsaw"))
    assert render_clock_header(local_dt) == "🕒 [2026-08-04 00:04]"
    assert render_clock_header(None) == "🕒 [ZEGAR NIEDOSTĘPNY]"


def test_visible_message_appearance_has_one_canonical_shape() -> None:
    assert render_visible_message(
        clock_header="🕒 [2026-08-04 00:04]",
        state_emoticon="🐾",
        author_label=AUTHOR,
        body="Treść wiadomości.",
    ) == "🕒 [2026-08-04 00:04]\n🐾 Łatka\n\nTreść wiadomości."


def test_warsaw_clock_prefers_environment_and_does_not_probe_network(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = WarsawClock()
    environment_sample = TimeSample(
        datetime(2026, 8, 4, 0, 4, tzinfo=ZoneInfo("Europe/Warsaw")),
        "environment_clock",
        False,
    )
    network_called = False

    monkeypatch.setattr(clock, "_injected_trusted_time", lambda: None)
    monkeypatch.setattr(clock, "_environment_time_sample", lambda: environment_sample)

    def _network_time(**_kwargs):
        nonlocal network_called
        network_called = True
        return None

    monkeypatch.setattr(clock, "_network_time", _network_time)
    assert clock.now() is environment_sample
    assert network_called is False


def test_warsaw_clock_uses_network_only_when_environment_clock_is_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = WarsawClock()
    network_sample = TimeSample(
        datetime(2026, 8, 4, 0, 4, tzinfo=ZoneInfo("Europe/Warsaw")),
        "https://time.example/api",
        True,
    )
    monkeypatch.setattr(clock, "_injected_trusted_time", lambda: None)
    monkeypatch.setattr(clock, "_environment_time_sample", lambda: None)
    monkeypatch.setattr(clock, "_network_time", lambda **_kwargs: network_sample)
    assert clock.now() is network_sample


def test_network_fallback_can_be_disabled_by_environment_policy(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = WarsawClock()
    network_called = False
    monkeypatch.setattr(clock, "_injected_trusted_time", lambda: None)
    monkeypatch.setattr(clock, "_environment_time_sample", lambda: None)

    def _network_time(**_kwargs):
        nonlocal network_called
        network_called = True
        return None

    monkeypatch.setattr(clock, "_network_time", _network_time)
    sample = clock.now(allow_network_fallback=False)
    assert sample.dt is None
    assert network_called is False


def test_network_sample_remains_usable_without_environment_freshness_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    resolver = TimeSourceResolver("Europe/Warsaw")
    sample = TimeSample(
        datetime(2026, 8, 4, 0, 4, tzinfo=ZoneInfo("Europe/Warsaw")),
        "https://time.example/api",
        True,
    )
    monkeypatch.setattr(WarsawClock, "_safe_utc_now", staticmethod(lambda: None))
    resolved = resolver.resolve(sample)
    assert resolved.clock_available is True
    assert resolved.timestamp_source == "network"
    assert resolved.timestamp_trusted is True
    assert resolved.human_time_header == "🕒 [2026-08-04 00:04]"


def test_no_clock_from_any_source_renders_unavailable_and_keeps_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = WarsawClock()
    monkeypatch.setattr(clock, "_injected_trusted_time", lambda: None)
    monkeypatch.setattr(clock, "_environment_time_sample", lambda: None)
    monkeypatch.setattr(clock, "_network_time", lambda **_kwargs: None)
    sample = clock.now()
    contract = clock.sample_contract(sample)
    assert sample.dt is None
    assert contract["clock_available"] is False
    assert contract["sample_iso"] is None
    assert contract["timestamp_header"] == CLOCK_UNAVAILABLE_HEADER


def test_message_envelope_accepts_unavailable_clock_without_fake_sample() -> None:
    envelope = MessageEnvelope.build(
        timestamp_header=CLOCK_UNAVAILABLE_HEADER,
        timezone="Europe/Warsaw",
        timestamp_sample_iso=None,
        timestamp_source="unavailable",
        timestamp_trusted=False,
        author_id="latka_runtime",
        author_label=AUTHOR,
        author_source="jazn_runtime",
        state_emoticon=MARKER,
        body=BODY,
    )
    assert envelope.timestamp_matches_sample() is True
    assert envelope.render() == f"{CLOCK_UNAVAILABLE_HEADER}\n{MARKER} {AUTHOR}\n\n{BODY}"


def test_unavailable_clock_is_diagnostic_only_for_integrity_and_truth_gate() -> None:
    decision = _unavailable_decision()
    contract = FinalResponseContract.build(
        turn_id="turn-no-clock",
        trace_id="trace-no-clock",
        runtime_version=PACKAGE_VERSION,
        timestamp_header=CLOCK_UNAVAILABLE_HEADER,
        timezone="Europe/Warsaw",
        state_emoticon=MARKER,
        body=BODY,
        conversation_decision=decision,
    ).to_dict()
    result = {
        "trace": {"timestamp_header": CLOCK_UNAVAILABLE_HEADER},
        "conversation_decision": decision,
        "final_response_contract": contract,
        "final_visible_text": contract["final_visible_text"],
        "runtime_provenance": decision["runtime_provenance"],
        "exact_runtime_text": BODY,
    }
    integrity = validate_result_integrity(result)
    assert integrity["valid"] is True
    assert integrity["clock_available"] is False
    assert integrity["blocking_errors"] == []

    updated, gate = apply_runtime_truth_gate(result)
    assert gate["ok"] is True
    assert gate["normal_response_allowed"] is True
    assert gate["time_trust_state"] == "clock_unavailable"
    assert updated["final_visible_text"] == contract["final_visible_text"]


def test_host_finalization_accepts_body_when_clock_is_unavailable() -> None:
    result = finalize_host_visible_text(
        required_timestamp_header=CLOCK_UNAVAILABLE_HEADER,
        timezone="Europe/Warsaw",
        timestamp_sample_iso=None,
        timestamp_source="unavailable",
        timestamp_trusted=False,
        author_id="latka_runtime",
        author_label=AUTHOR,
        author_source="jazn_runtime",
        state_emoticon=MARKER,
        turn_id="turn-no-clock",
        trace_id="trace-no-clock",
        text=BODY,
        supplied_turn_id="turn-no-clock",
        supplied_trace_id="trace-no-clock",
        supplied_text_sha256=hashlib.sha256(BODY.encode()).hexdigest(),
    )
    assert result.accepted is True
    assert result.final_visible_text == f"{CLOCK_UNAVAILABLE_HEADER}\n{MARKER} {AUTHOR}\n\n{BODY}"
