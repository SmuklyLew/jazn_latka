"""Regression for stable daemon-result provenance and explicit live diagnostics.

No daemon is started; all live status calls are isolated test doubles.
"""
from __future__ import annotations

from pathlib import Path

import main as main_module
from latka_jazn.config import JaznConfig
from latka_jazn.core.handlers.capability_status_handler import CapabilityStatusHandler
from latka_jazn.core import runtime_daemon
from latka_jazn.nlp.dialogue_intent_classifier import DialogueIntentClassifier
from latka_jazn.version import PACKAGE_VERSION_FULL


def _live_status(root: Path) -> dict:
    return {
        "active_state": "active_degraded",  # clock trust may be degraded
        "runtime_version_full": PACKAGE_VERSION_FULL,
        "endpoint_reachable": True,
        "endpoint_identity_matches": True,
        "process_identity_confirmed": True,
        "heartbeat_fresh": True,
        "package_integrity_verified": True,
        "source_provenance_verified": True,
        "daemon_instance_id": "instance-922",
        "resolved_active_root": str(root),
        "pid": 922,
        "ping_endpoint": "http://127.0.0.1:8787/status",
        "ping": {"conversation_ready": True},
    }


def test_explicit_daemon_process_fields_precede_package_route() -> None:
    classifier = DialogueIntentClassifier()
    report = classifier.classify(
        "Podaj PID demona, daemon_instance_id i conversation_ready; "
        "nie sprawdzaj ponownie archiwum ZIP."
    )
    assert report.primary_intent == "runtime_health_check"


def test_real_package_integrity_request_stays_package_route() -> None:
    report = DialogueIntentClassifier().classify(
        "Sprawdź archiwum ZIP, manifest i SHA256 paczki. Czy runtime działa?"
    )
    assert report.primary_intent == "package_runtime_status_question"


def test_live_diagnostics_report_daemon_pid_not_cli_pid(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(runtime_daemon, "status_daemon", lambda *_a, **_kw: _live_status(tmp_path))
    result = CapabilityStatusHandler().handle(
        "Podaj PID demona, daemon_instance_id oraz conversation_ready.",
        context={"config": JaznConfig(root=tmp_path), "intent": "runtime_health_check"},
    )
    assert "daemon_identity_verified=True" in result.body
    assert "daemon_pid=922" in result.body
    assert "daemon_instance_id=instance-922" in result.body
    assert "conversation_ready=True" in result.body
    assert "source_origin=live_status_daemon_read_only" in result.body


def test_live_diagnostics_fail_closed_on_identity_mismatch(tmp_path: Path, monkeypatch) -> None:
    bad = _live_status(tmp_path)
    bad["endpoint_identity_matches"] = False
    monkeypatch.setattr(runtime_daemon, "status_daemon", lambda *_a, **_kw: bad)
    result = CapabilityStatusHandler().handle(
        "Podaj PID demona i daemon_instance_id.",
        context={"config": JaznConfig(root=tmp_path), "intent": "runtime_health_check"},
    )
    assert "daemon_identity_verified=False" in result.body
    assert "daemon_pid=not_verified" in result.body
    assert "daemon_instance_id=not_verified" in result.body


def test_poll_transport_reverified_with_clock_degraded_but_live_daemon(
    tmp_path: Path, monkeypatch
) -> None:
    marker = tmp_path / "JAZN_ACTIVE_RUNTIME.json"
    marker.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(main_module, "_chatgpt_daemon_marker_path", lambda _cfg: marker)
    monkeypatch.setattr(main_module, "status_daemon", lambda *_a, **_kw: _live_status(tmp_path))
    evidence = main_module._verified_daemon_poll_transport(
        cfg=JaznConfig(root=tmp_path), host="127.0.0.1", port=8787
    )
    assert evidence["selected_transport"] == "persistent_daemon"
    assert evidence["transport_evidence_origin"] == "retrieval_live_status"
    assert evidence["daemon_instance_id"] == "instance-922"


def test_poll_transport_missing_or_mismatched_identity_not_promoted(
    tmp_path: Path, monkeypatch
) -> None:
    marker = tmp_path / "JAZN_ACTIVE_RUNTIME.json"
    marker.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(main_module, "_chatgpt_daemon_marker_path", lambda _cfg: marker)
    bad = _live_status(tmp_path)
    bad["heartbeat_fresh"] = False
    monkeypatch.setattr(main_module, "status_daemon", lambda *_a, **_kw: bad)
    assert not main_module._verified_daemon_poll_transport(
        cfg=JaznConfig(root=tmp_path), host="127.0.0.1", port=8787
    )


def test_completed_result_attaches_only_reverified_retrieval_evidence(
    tmp_path: Path, monkeypatch
) -> None:
    # This verifies the presentation seam, without submitting a new message.
    monkeypatch.setattr(
        main_module, "_resolve_daemon_user_text_binding",
        lambda **_kwargs: ("Podaj PID demona.", None),
    )
    monkeypatch.setattr(main_module, "attach_chatgpt_host_contract", lambda *_a, **_kw: None)
    payload = {
        "done": True,
        "request_id": "same-request",
        "result": {
            "final_visible_text": "unchanged",
            "turn_id": "same-turn",
            "trace_id": "same-request",
        },
    }
    result = main_module._prepare_chatgpt_daemon_presentation(
        cfg=JaznConfig(root=tmp_path),
        payload=payload,
        request_id="same-request",
        retrieval_transport_observability={
            "selected_transport": "persistent_daemon",
            "transport_evidence_origin": "retrieval_live_status",
        },
    )
    assert result["final_visible_text"] == "unchanged"
    assert result["turn_id"] == "same-turn"
    assert result["retrieval_transport_observability"]["selected_transport"] == "persistent_daemon"
    assert result["chat_bridge"]["transport_observability"]["transport_evidence_origin"] == "retrieval_live_status"
    assert payload["result"].get("transport_observability") is None


def test_completed_result_does_not_invent_transport_without_attestation(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(
        main_module, "_resolve_daemon_user_text_binding",
        lambda **_kwargs: ("Podaj PID demona.", None),
    )
    monkeypatch.setattr(main_module, "attach_chatgpt_host_contract", lambda *_a, **_kw: None)
    result = main_module._prepare_chatgpt_daemon_presentation(
        cfg=JaznConfig(root=tmp_path),
        payload={"done": True, "result": {"final_visible_text": "same"}},
        request_id="same-request",
    )
    assert not result.get("transport_observability")
    assert not result.get("retrieval_transport_observability")


def test_poll_transport_rejects_other_release_or_recorded_instance(
    tmp_path: Path, monkeypatch
) -> None:
    marker = tmp_path / "JAZN_ACTIVE_RUNTIME.json"
    marker.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(main_module, "_chatgpt_daemon_marker_path", lambda _cfg: marker)
    live = _live_status(tmp_path)
    monkeypatch.setattr(main_module, "status_daemon", lambda *_a, **_kw: live)
    cfg = JaznConfig(root=tmp_path)
    assert not main_module._verified_daemon_poll_transport(
        cfg=cfg, host="127.0.0.1", port=8787,
        payload={"result": {"daemon_instance_id": "a-different-instance"}},
    )
    live["runtime_version_full"] = "16.3.25.5.116.0.34.27-isolated-mcp-oauth-staging"
    assert not main_module._verified_daemon_poll_transport(
        cfg=cfg, host="127.0.0.1", port=8787,
    )
