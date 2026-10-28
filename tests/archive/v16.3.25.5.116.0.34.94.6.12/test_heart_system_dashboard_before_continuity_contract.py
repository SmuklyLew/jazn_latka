"""Dashboard consumes canonical observations, including negative CLI exits."""
from __future__ import annotations
import json
from pathlib import Path
import queue
import pytest
from tools.jazn_run_studio.core import Controller
from tools.jazn_run_studio.status_summary import status_summary


def observation() -> dict:
    return {"runtime_version": "16.3-test", "daemon": {
        "package_integrity_verified": True, "package_integrity_verification": {"ok": True},
        "source_provenance_verified": True,
    }, "memory_availability": {"status": "disabled_by_policy", "mode": "off", "ok": True,
                                "memory_root": "/private/database"},
    "startup": {"model_adapter_status": {"selected_backend_adapter": "null_model_adapter"}}}


def test_summary_separates_integrity_memory_and_null_model() -> None:
    result = status_summary(observation())
    assert result["version"] == "16.3-test"
    assert result["integrity"] == result["provenance"] == "zweryfikowane"
    assert "wyłączona" in result["memory"] and "recall i ciągłość" in result["memory"]
    assert "brak backendu generacyjnego" in result["model"]
    assert "/private/database" not in json.dumps(result)
    assert set(result) == {"version", "integrity", "provenance", "memory", "model"}


@pytest.mark.parametrize("proof, expected", [(True, "niezweryfikowane"), ("true", "niezweryfikowane"), (False, "błąd weryfikacji")])
def test_integrity_flag_requires_actual_manifest_result(proof, expected: str) -> None:
    data = {"daemon": {"package_integrity_verified": proof}}
    assert status_summary(data)["integrity"] == expected


def test_available_configured_model_is_not_verified_generation() -> None:
    data = observation()
    data["startup"]["model_adapter_status"] = {"selected_backend_adapter": "local_llm_adapter",
        "model_name": "gemma3:latest", "available": True, "configured": True, "validated": True}
    result = status_summary(data)
    assert "gemma3:latest" in result["model"] and "generacja niezweryfikowana" in result["model"]


def test_malformed_shapes_remain_unknown() -> None:
    result = status_summary({"daemon": [], "startup": None, "memory_availability": {"mode": {}}})
    assert result["integrity"] == "niezweryfikowane"
    assert result["provenance"] == "niezweryfikowane"


@pytest.mark.parametrize("valid_json", [True, False])
def test_real_negative_child_status_emits_observation_and_keeps_failure(tmp_path: Path, valid_json: bool) -> None:
    (tmp_path / "latka_jazn").mkdir()
    (tmp_path / "latka_jazn/version.py").touch()
    (tmp_path / "main.py").touch()
    data = observation()
    data["daemon"].update(active_state="inactive", package_integrity_verified=False)
    output = json.dumps(data) if valid_json else "not a status response"
    (tmp_path / "run.py").write_text("print(" + repr(output) + "); raise SystemExit(1)", encoding="utf-8")
    core = Controller(tmp_path)
    job = core.start_action("status")
    assert job.done.wait(10)
    assert job.state == "failed" and job.returncode == 1
    assert job.error == ("process_exit:1" if valid_json else "invalid_status_json")
    events = []
    while True:
        try: events.append(core.events.get_nowait())
        except queue.Empty: break
    evidence = next(value for _, kind, value in events if kind == "evidence")
    summary = next(value for _, kind, value in events if kind == "status_summary")
    assert evidence["endpoint_reachable"] is False and evidence["accepted_visible_turn"] is False
    assert evidence["active_state"] == ("inactive" if valid_json else None)
    assert summary["integrity"] == ("błąd weryfikacji" if valid_json else "niezweryfikowane")
