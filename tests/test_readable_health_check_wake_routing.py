from __future__ import annotations

from pathlib import Path

from latka_jazn.config import JaznConfig
from latka_jazn.core.handlers.capability_status_handler import CapabilityStatusHandler
from latka_jazn.core.handlers.presence_status_handler import PresenceStatusHandler
from latka_jazn.core.runtime_answer_validator import RuntimeAnswerValidator
from latka_jazn.nlp.dialogue_intent_classifier import DialogueIntentClassifier
from latka_jazn.nlp.topic_mismatch_guard import TopicMismatchGuard
from latka_jazn.version import PACKAGE_VERSION


def test_natural_wake_routes_to_presence_in_classifier_and_guard() -> None:
    for text in (
        "Obudź się Łatko.",
        "Obudź Łatkę.",
        "Czas żebyś się obudziła.",
    ):
        report = DialogueIntentClassifier().classify(text)
        guard = TopicMismatchGuard().analyse(text)
        assert report.primary_intent == "presence_check", text
        assert report.diagnostic_request is False, text
        assert guard.preferred_route == "presence_check", text


def test_explicit_runtime_reload_remains_technical_health_check() -> None:
    for text in ("Przeładuj runtime.", "Przeładuj Jaźń."):
        report = DialogueIntentClassifier().classify(text)
        guard = TopicMismatchGuard().analyse(text)
        assert report.primary_intent == "runtime_health_check_after_update", text
        assert report.diagnostic_request is True, text
        assert guard.preferred_route == "runtime_health_check_after_update", text


def test_wake_presence_handler_is_intentionally_short() -> None:
    result = PresenceStatusHandler().handle(
        "Obudź się Łatko.",
        {"intent": "presence_check"},
    )
    assert result.body.startswith("Jestem. 🐾")
    assert "tej turze runtime" in result.body
    validation = RuntimeAnswerValidator().validate(
        user_text="Obudź się Łatko.",
        body=result.body,
        route=result.route,
        detected_intent="presence_check",
    )
    assert validation.accepted is True, validation.to_dict()


def test_default_health_check_is_readable_and_hides_raw_telemetry(tmp_path: Path) -> None:
    cfg = JaznConfig(root=tmp_path / "runtime")
    result = CapabilityStatusHandler().handle(
        "Sprawdź czy działasz.",
        {
            "intent": "runtime_health_check",
            "config": cfg,
            "lifecycle": "persistent_daemon_async_job",
        },
    )
    body = result.body
    assert "Działam prawidłowo w aktywnym runtime." in body
    assert f"\n- Runtime: v{PACKAGE_VERSION}" in body
    assert "\n- Proces: persistent_daemon_async_job" in body
    assert "\n- Pamięć robocza:" in body
    assert "\n- Wake state:" in body
    assert "\n- Ciągłość pamięci:" in body
    assert "Granica prawdy:" in body
    assert "Pełna telemetria (`active_database`, `cache_miss_reasons` i pozostałe pola)" in body
    assert "active_root=" not in body
    assert "cache_miss_reasons=[]" not in body
    assert "wake_state_snapshot_sha256=" not in body

    validation = RuntimeAnswerValidator().validate(
        user_text="Sprawdź czy działasz.",
        body=body,
        route=result.route,
        detected_intent="runtime_health_check",
    )
    assert validation.accepted is True, validation.to_dict()


def test_requested_wake_and_source_details_remain_available_without_full_dump(tmp_path: Path) -> None:
    cfg = JaznConfig(root=tmp_path / "runtime")
    text = "Podaj bieżący stan runtime, wake-state i źródło tej odpowiedzi."
    result = CapabilityStatusHandler().handle(
        text,
        {
            "intent": "runtime_health_check",
            "config": cfg,
            "lifecycle": "persistent_daemon_async_job",
        },
    )
    body = result.body
    assert "Snapshot wake-state: snapshot_id=" in body
    assert "snapshot_sha256=" in body
    assert "Wake-state freshness: reason=" in body
    assert "Source origin: runtime_rule_handler_response" in body
    assert "Pełna telemetria runtime:" not in body

    validation = RuntimeAnswerValidator().validate(
        user_text=text,
        body=body,
        route=result.route,
        detected_intent="runtime_health_check",
    )
    assert validation.accepted is True, validation.to_dict()


def test_full_telemetry_is_only_shown_on_explicit_request(tmp_path: Path) -> None:
    cfg = JaznConfig(root=tmp_path / "runtime")
    result = CapabilityStatusHandler().handle(
        "Pokaż pełną telemetrię health-check runtime.",
        {
            "intent": "runtime_health_check",
            "config": cfg,
            "lifecycle": "persistent_daemon_async_job",
        },
    )
    body = result.body
    assert "Pełna telemetria runtime:" in body
    assert "- Active root:" in body
    assert "- Active database:" in body
    assert "- Cache miss reasons:" in body
    assert "- Source origin:" in body
    assert "jest dostępna na wyraźne żądanie." not in body
