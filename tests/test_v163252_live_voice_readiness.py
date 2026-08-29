from __future__ import annotations

import json
from pathlib import Path

from latka_jazn.config import JaznConfig
from latka_jazn.core import startup_contract


ROOT = Path(__file__).resolve().parents[1]


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
