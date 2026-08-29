from __future__ import annotations

import json
from pathlib import Path

import pytest

from latka_jazn.config import JaznConfig
from latka_jazn.core import startup_contract
from latka_jazn.core.chatgpt_host_pre_response_gate import run_host_pre_response_gate


ROOT = Path(__file__).resolve().parents[1]
VOICE_HEADER = "🕒 2026-08-29 18:00:00"


def _dead_daemon_status(root: Path) -> dict[str, object]:
    return {
        "active_state": "inactive",
        "runtime_active_state": "inactive",
        "pid": 2_147_483_647,
        "pid_alive": False,
        "process_identity_confirmed": False,
        "endpoint_probe_performed": True,
        "endpoint_reachable": False,
        "endpoint_pid_matches": False,
        "endpoint_root_matches": False,
        "endpoint_identity_matches": False,
        "heartbeat_fresh": False,
        "resolved_active_root": str(root.resolve()),
        "subject_runtime_root": str(root.resolve()),
        "package_integrity_verified": True,
        "source_provenance_verified": True,
        "active_state_reason": "daemon_process_not_confirmed",
    }


def _voice_presentation(
    *,
    index: int,
    author_source: str = "jazn_runtime",
    transport_overrides: dict[str, object] | None = None,
) -> dict[str, object]:
    turn_id = f"turn-v163252-{index}"
    trace_id = f"trace-v163252-{index}"
    final_text = f"{VOICE_HEADER}\n🌿 Łatka\nSyntetyczna odpowiedź {index}."
    transport: dict[str, object] = {
        "selected_transport": "persistent_daemon",
        "fallback_reason": "daemon_reused",
        "requested_runtime_root": str(ROOT.resolve()),
        "resolved_active_root": str(ROOT.resolve()),
        "daemon_endpoint_root": str(ROOT.resolve()),
        "daemon_identity_verified": True,
        "daemon_pid": 4242,
        "daemon_reused": True,
        "daemon_started": False,
        "one_shot_verified": False,
    }
    transport.update(transport_overrides or {})
    return {
        "type": "chatgpt_host_presentation",
        "action": "display_exact",
        "phase": "runtime_final_available",
        "turn_id": turn_id,
        "trace_id": trace_id,
        "author_source": author_source,
        "final_visible_text": final_text,
        "chatgpt_host_bridge": {
            "turn_id": turn_id,
            "trace_id": trace_id,
            "required_visible_prefix": VOICE_HEADER,
        },
        "transport_observability": transport,
    }


def test_stale_marker_and_dead_daemon_never_activate_latka_voice(
    tmp_path: Path,
    monkeypatch,
) -> None:
    marker = tmp_path / "JAZN_ACTIVE_RUNTIME.json"
    marker.write_text(
        json.dumps(
            {
                "active_root": str(ROOT.resolve()),
                "daemon_pid": 2_147_483_647,
                "daemon_host": "127.0.0.1",
                "daemon_port": 65534,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        startup_contract,
        "build_active_runtime_status",
        lambda *_args, **_kwargs: {
            "active_root": str(ROOT.resolve()),
            "runtime_root_valid": True,
            "existing_marker_found": True,
            "active_marker_valid": True,
            "marker_output": str(marker),
        },
    )
    # Current master probes only /ready here; the hotfix replaces this boolean
    # shortcut with canonical daemon identity/readiness evidence.
    monkeypatch.setattr(
        startup_contract,
        "_daemon_ready_from_active_marker",
        lambda *_args, **_kwargs: False,
        raising=False,
    )
    monkeypatch.setattr(
        startup_contract,
        "_daemon_status_from_active_marker",
        lambda *_args, **_kwargs: _dead_daemon_status(ROOT),
        raising=False,
    )

    status = startup_contract.build_startup_status(
        JaznConfig(root=ROOT, allow_network=False),
        mode="fast",
    ).to_dict()

    assert status["active_cache_status"]["active_marker_valid"] is True
    assert status["daemon_ready"] is False
    assert status["voice_configured"] is True
    assert status["voice_live_ready"] is False
    assert status["voice_e2e_verified"] is False
    assert status["voice_ready"] is False
    assert "pid_not_alive" in status["voice_live_readiness_status"]["blocking_reasons"]
    assert "endpoint_unreachable" in status["voice_live_readiness_status"]["blocking_reasons"]
    voice = status["voice_source_contract_status"]
    assert voice["chatgpt_may_speak_as_voice"] is False
    assert voice["voice_live_ready"] is False
    assert voice["active_source"] != "jazn_runtime"


def test_two_exact_turns_are_e2e_verified_on_the_same_daemon() -> None:
    exact_user_turns = ["Jak się teraz miewasz?", "A teraz druga zwykła tura."]
    invoked: list[str] = []

    def invoke(text: str) -> dict[str, object]:
        invoked.append(text)
        return _voice_presentation(index=len(invoked))

    first = run_host_pre_response_gate(
        exact_user_turns[0],
        invoke_runtime=invoke,
        requested_runtime_root=ROOT,
    )
    second = run_host_pre_response_gate(
        exact_user_turns[1],
        invoke_runtime=invoke,
        requested_runtime_root=ROOT,
    )

    assert invoked == exact_user_turns
    assert first["action"] == second["action"] == "display_exact"
    assert first["visible_output_source"] == second["visible_output_source"] == "runtime_exact"
    assert first["voice_e2e_verified"] is second["voice_e2e_verified"] is True
    first_e2e = first["voice_e2e_verification"]
    second_e2e = second["voice_e2e_verification"]
    assert first_e2e["daemon_pid"] == second_e2e["daemon_pid"] == 4242
    assert first_e2e["subject_root"] == second_e2e["subject_root"] == str(ROOT.resolve())
    assert first_e2e["runtime_turn_id"] != second_e2e["runtime_turn_id"]
    assert first_e2e["trace_id"] != second_e2e["trace_id"]
    assert first_e2e["author_source"] == second_e2e["author_source"] == "jazn_runtime"
    assert first_e2e["scope"] == second_e2e["scope"] == "current_turn_only"


@pytest.mark.parametrize(
    ("transport_overrides", "author_source", "expected_reason"),
    [
        (
            {"daemon_identity_verified": False},
            "jazn_runtime",
            "daemon_identity_not_verified",
        ),
        ({"daemon_pid": None}, "jazn_runtime", "daemon_identity_not_verified"),
        (
            {"daemon_endpoint_root": str(ROOT / "other-runtime")},
            "jazn_runtime",
            "subject_root_not_bound",
        ),
        ({}, "host_chatgpt", "author_source_not_jazn_runtime"),
    ],
)
def test_incomplete_persistent_voice_e2e_is_host_diagnostic(
    transport_overrides: dict[str, object],
    author_source: str,
    expected_reason: str,
) -> None:
    result = run_host_pre_response_gate(
        "Dokładna syntetyczna tura.",
        invoke_runtime=lambda _text: _voice_presentation(
            index=1,
            author_source=author_source,
            transport_overrides=transport_overrides,
        ),
        requested_runtime_root=ROOT,
    )

    assert result["ok"] is False
    assert result["action"] == "host_diagnostic"
    assert result["visible_output_source"] == "host_diagnostic"
    assert result["voice_e2e_verified"] is False
    assert expected_reason in result["failed_voice_e2e_verification"]["blocking_reasons"]
    assert "🌿 Łatka" not in result["visible_text"]
