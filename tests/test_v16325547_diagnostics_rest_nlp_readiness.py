from __future__ import annotations

from pathlib import Path

from latka_jazn.cli import build_parser
from latka_jazn.cli_commands import diagnostics


class _Startup:
    def to_dict(self):
        return {
            "voice_live_ready": False,
            "dictionary_provider_status": {},
            "conversation_archive_status": {},
            "memory_continuity_status": {},
            "model_adapter_status": {},
            "runtime_write_access_status": {},
            "active_cache_status": {},
        }


class _LivingMemory:
    def __init__(self, _root):
        pass

    def readiness(self):
        return {"status": "ready_transactional_tier_only", "memory_search_ready": True, "legacy_search_ready": False}


class _ProbeReport:
    def __init__(self, mode: str):
        self.mode = mode

    def to_dict(self):
        deep = self.mode == "deep"
        return {
            "schema_version": "nlp_runtime_capability_probe/v1",
            "mode": self.mode,
            "status": "enhanced_ready" if deep else "core_ready_enhanced_probe_not_requested",
            "core_probe_executed": True,
            "core_ready": True,
            "enhanced_probe_requested": deep,
            "enhanced_probe_executed": deep,
            "enhanced_ready": deep,
            "stanza": {"pipeline_call_performed": deep, "available": deep},
        }


def _patch_status_dependencies(monkeypatch, observed_modes: list[str]) -> None:
    monkeypatch.setattr(diagnostics, "build_startup_status", lambda *_args, **_kwargs: _Startup())
    monkeypatch.setattr(
        diagnostics,
        "status_daemon",
        lambda *_args, **_kwargs: {
            "active_state": "active_trusted",
            "endpoint_reachable": True,
            "runtime_write_ready": True,
        },
    )
    monkeypatch.setattr(
        diagnostics,
        "_probe_daemon_readiness",
        lambda *_args, **_kwargs: {
            "ok": True,
            "endpoint": "/ready",
            "rest_cycle_status": {
                "enabled": True,
                "state": "waiting_for_idle",
                "rest_scheduler_ready": True,
                "rest_scheduler_running": True,
            },
        },
    )
    monkeypatch.setattr(diagnostics, "_transactional_memory_status", lambda _cfg: {"ready": True})
    monkeypatch.setattr(diagnostics, "LivingMemoryGateway", _LivingMemory)

    def fake_probe(_root, *, mode="fast"):
        observed_modes.append(mode)
        return _ProbeReport(mode)

    monkeypatch.setattr(diagnostics, "probe_nlp_runtime_capability", fake_probe)


def test_status_binds_rest_ready_and_executes_fast_nlp_probe(tmp_path: Path, monkeypatch) -> None:
    modes: list[str] = []
    _patch_status_dependencies(monkeypatch, modes)

    payload = diagnostics.status_payload(tmp_path, probe_endpoint=True)

    assert modes == ["fast"]
    rest = payload["system_readiness_profile"]["capabilities"]["rest_scheduler"]
    assert rest["ready"] is True
    assert rest["status"] == "waiting_for_idle"
    assert payload["capability_readiness"]["rest_scheduler_running"] is True
    assert payload["capability_readiness"]["rest_scheduler_evidence_source"] == "daemon.readiness.rest_cycle_status"

    core = payload["system_readiness_profile"]["capabilities"]["nlp_core"]
    enhanced = payload["system_readiness_profile"]["capabilities"]["nlp_enhanced"]
    assert core["ready"] is True
    assert payload["capability_readiness"]["nlp_core_probe_executed"] is True
    assert enhanced["ready"] is False
    assert enhanced["status"] == "core_ready_enhanced_probe_not_requested"
    assert payload["capability_readiness"]["nlp_enhanced_probe_executed"] is False


def test_status_deep_mode_can_only_report_enhanced_after_executed_probe(tmp_path: Path, monkeypatch) -> None:
    modes: list[str] = []
    _patch_status_dependencies(monkeypatch, modes)

    payload = diagnostics.status_payload(tmp_path, probe_endpoint=True, nlp_probe_mode="deep")

    assert modes == ["deep"]
    enhanced = payload["system_readiness_profile"]["capabilities"]["nlp_enhanced"]
    assert enhanced["ready"] is True
    assert payload["capability_readiness"]["nlp_enhanced_probe_requested"] is True
    assert payload["capability_readiness"]["nlp_enhanced_probe_executed"] is True
    assert payload["capability_readiness"]["nlp_enhanced_ready"] is True


def test_doctor_cli_exposes_explicit_deep_capability_probe_switch() -> None:
    ns = build_parser().parse_args(["doctor", "--deep-capability-probes", "--json"])
    assert ns.command == "doctor"
    assert ns.deep_capability_probes is True
