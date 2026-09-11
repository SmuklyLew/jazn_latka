from __future__ import annotations

import io
import json
from pathlib import Path

import main as main_module
from latka_jazn.config import JaznConfig
from latka_jazn.core import bridge_discovery, runtime_daemon
from latka_jazn.version import PACKAGE_RELEASE_NAME, PACKAGE_VERSION


def _packet(text: str) -> dict:
    return json.loads(text.strip().splitlines()[-1])


def test_submit_transport_failure_preserves_request_id_when_status_probe_also_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    # main import installs the turn-authority overlay before binding daemon helpers.
    # Its submit wrapper must keep the caller-provided id even when the legacy
    # submit path raises while trying to diagnose a lost response.
    wrapped_submit = runtime_daemon.chat_daemon_submit
    monkeypatch.setattr(
        runtime_daemon,
        "http_json",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("submit response lost")),
    )
    monkeypatch.setattr(
        runtime_daemon,
        "status_daemon",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("status unavailable")),
    )

    payload = wrapped_submit(
        JaznConfig(root=tmp_path),
        "test transport ambiguity",
        request_id="request-v63-preserved",
        session_id="session-v63",
    )

    assert payload["ok"] is False
    assert payload["accepted"] is False
    assert payload["error_code"] == "daemon_chat_submit_failed"
    assert payload["request_id"] == "request-v63-preserved"
    assert payload["submit_outcome_authoritative"] is False
    assert payload["safe_recovery"] == "poll_same_request_id_before_any_retry"


def test_verified_daemon_transport_exception_becomes_poll_same_request_not_local_fallback(
    tmp_path: Path,
    monkeypatch,
) -> None:
    marker = tmp_path / "JAZN_ACTIVE_RUNTIME.json"
    marker.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(main_module, "_chatgpt_daemon_marker_path", lambda _cfg: marker)
    monkeypatch.setattr(
        main_module,
        "status_daemon",
        lambda *_args, **_kwargs: {
            "active_state": "active_trusted",
            "endpoint_reachable": True,
        },
    )
    monkeypatch.setattr(
        main_module,
        "chat_daemon",
        lambda *_args, **_kwargs: {
            "ok": False,
            "accepted": None,
            "done": False,
            "error_code": "daemon_chat_pending",
            "request_id": "request-v63-ambiguous",
            "client_wait_status": "submit_outcome_unknown",
        },
    )
    stdout = io.StringIO()
    monkeypatch.setattr(main_module.sys, "stdout", stdout)

    rc = main_module._try_chat_gpt_one_shot_via_daemon(
        cfg=JaznConfig(root=tmp_path),
        text="Nie twórz drugiej tury.",
        session_id="chatgpt-main",
        no_carryover=False,
        host="127.0.0.1",
        port=8787,
        timeout=1.0,
        output_mode="host_packet",
        request_id="request-v63-ambiguous",
        transport_observability={
            "selected_transport": "persistent_daemon",
            "fallback_reason": "daemon_reused",
            "requested_runtime_root": str(tmp_path),
            "resolved_active_root": str(tmp_path),
            "daemon_identity_verified": True,
        },
    )

    packet = _packet(stdout.getvalue())
    assert rc == 0
    assert packet["action"] == "poll_runtime"
    assert packet["daemon_request_id"] == "request-v63-ambiguous"
    assert packet["accepted_visible_turn_ready"] is False
    assert packet["must_not_claim_latka_voice"] is True
    assert packet["transport_observability"]["selected_transport"] == "persistent_daemon"
    assert "request-v63-ambiguous" in packet["poll_command"]


def test_verified_daemon_submit_failure_is_not_replayed_as_local_turn(
    tmp_path: Path,
    monkeypatch,
) -> None:
    marker = tmp_path / "JAZN_ACTIVE_RUNTIME.json"
    marker.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(main_module, "_chatgpt_daemon_marker_path", lambda _cfg: marker)
    monkeypatch.setattr(
        main_module,
        "status_daemon",
        lambda *_args, **_kwargs: {
            "active_state": "active_trusted",
            "endpoint_reachable": True,
        },
    )
    monkeypatch.setattr(
        main_module,
        "chat_daemon",
        lambda *_args, **_kwargs: {
            "ok": False,
            "accepted": None,
            "done": False,
            "error_code": "daemon_chat_pending",
            "error": "connection closed after POST",
            "request_id": "request-v63-submit",
            "client_wait_status": "submit_outcome_unknown",
        },
    )
    stdout = io.StringIO()
    monkeypatch.setattr(main_module.sys, "stdout", stdout)

    rc = main_module._try_chat_gpt_one_shot_via_daemon(
        cfg=JaznConfig(root=tmp_path),
        text="Zachowaj request.",
        session_id="chatgpt-main",
        no_carryover=False,
        host="127.0.0.1",
        port=8787,
        timeout=1.0,
        output_mode="host_packet",
        request_id="request-v63-submit",
        transport_observability={
            "selected_transport": "persistent_daemon",
            "fallback_reason": "daemon_reused",
            "requested_runtime_root": str(tmp_path),
        },
    )

    packet = _packet(stdout.getvalue())
    assert rc == 0
    assert packet["action"] == "poll_runtime"
    assert packet["daemon_request_id"] == "request-v63-submit"
    assert packet["chatgpt_host_bridge"]["phase"] == "runtime_result_pending"


def test_bridge_discovery_exposes_nonstreaming_daemon_bound_transport(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        bridge_discovery,
        "status_daemon",
        lambda *_args, **_kwargs: {"active_state": "inactive"},
    )
    payload = bridge_discovery.discover_runtime_bridges(JaznConfig(root=tmp_path))
    chatgpt = payload["chatgpt_bridge"]

    assert chatgpt["transport"] == "persistent_stdio_jsonl"
    assert chatgpt["fallback_transport"] == "daemon_bound_transactional_turns"
    assert chatgpt["persistent_stdio_required"] is False
    assert chatgpt["per_message_cli_allowed_when_host_cannot_retain_stdio"] is True
    assert chatgpt["request_id_preallocated_before_process_spawn"] is True
    assert chatgpt["ambiguous_transport_policy"] == "poll_same_request_id_never_local_replay"
    assert "--daemon-request-id" in chatgpt["nonstreaming_turn_command"]
    assert "--daemon-result" in chatgpt["nonstreaming_resume_command"]


def test_chatgpt_runbook_and_loader_document_streaming_host_fallback() -> None:
    root = Path(__file__).resolve().parents[1]
    runbook = (root / "AGENTS.chatgpt.md").read_text(encoding="utf-8")
    loader = (root / "docs/runtime/CHATGPT_PROJECT_INSTRUCTIONS.txt").read_text(encoding="utf-8")

    assert "StreamingExecNotEnabledContainerError" in runbook
    assert "--daemon-request-id" in runbook
    assert "--daemon-request-id" in loader
    assert "nie może spaść do niezależnej lokalnej tury" in loader


def test_v63_transport_convergence_remains_in_current_or_newer_release() -> None:
    assert tuple(int(part) for part in PACKAGE_VERSION.split(".")) >= (16, 3, 25, 5, 63)
    assert PACKAGE_RELEASE_NAME
