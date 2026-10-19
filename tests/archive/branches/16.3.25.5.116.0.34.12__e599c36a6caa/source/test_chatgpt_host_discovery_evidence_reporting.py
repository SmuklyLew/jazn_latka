from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

from latka_jazn.bootstrap.chatgpt_host_preflight import (
    HostDiscoveryEvidence,
    plan_chatgpt_host_preflight,
)
from latka_jazn.core.chatgpt_host_executor_contract import HostExecutorObservation


ROOT = Path(__file__).resolve().parents[1]


def _run_preflight(tmp_path: Path, payload: dict[str, object]) -> subprocess.CompletedProcess[str]:
    contract = tmp_path / "host-preflight.json"
    contract.write_text(json.dumps(payload), encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(ROOT / "run.py"), "host-preflight", "--input", str(contract), "--json"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        check=False,
    )


def _failed_executor_payload() -> list[dict[str, object]]:
    return [{
        "surface": "python_tool",
        "process_created": False,
        "error_class": "ClientError",
        "alternative_surface_available": False,
    }]


def test_fail_closed_preflight_reports_explicit_discovery_evidence(tmp_path: Path) -> None:
    completed = _run_preflight(
        tmp_path,
        {
            "executor_observations": _failed_executor_payload(),
            "library_search_available": True,
            "library_materialize_available": False,
            "system_search_attempted": True,
            "system_candidate_found": True,
        },
    )

    assert completed.returncode == 3, completed.stderr
    result = json.loads(completed.stdout)
    assert {
        key: result[key]
        for key in (
            "executor_available",
            "library_search_available",
            "library_materialize_available",
            "system_search_attempted",
            "system_candidate_found",
            "remote_runtime_available",
        )
    } == {
        "executor_available": False,
        "library_search_available": True,
        "library_materialize_available": False,
        "system_search_attempted": True,
        "system_candidate_found": True,
        "remote_runtime_available": None,
    }


def test_unreported_library_capabilities_remain_unknown_instead_of_false(tmp_path: Path) -> None:
    completed = _run_preflight(
        tmp_path,
        {
            "executor_observations": _failed_executor_payload(),
            "remote_runtime_available": True,
        },
    )

    assert completed.returncode == 3, completed.stderr
    result = json.loads(completed.stdout)
    assert result["executor_available"] is False
    assert result["remote_runtime_available"] is None
    assert result["library_search_available"] is None
    assert result["library_materialize_available"] is None
    assert result["system_search_attempted"] is None
    assert result["system_candidate_found"] is None


def test_remote_runtime_available_is_derived_from_verified_observation() -> None:
    decision = plan_chatgpt_host_preflight(
        [
            HostExecutorObservation(
                process_created=False,
                error_class="ClientError",
                surface="chat",
                remote_runtime_transport_available=True,
            )
        ],
        discovery_evidence=HostDiscoveryEvidence(
            library_search_available=False,
            library_materialize_available=False,
            system_search_attempted=False,
            system_candidate_found=False,
        ),
    )

    assert decision.executor_available is False
    assert decision.remote_runtime_available is True
    assert decision.remote_runtime_allowed is True


def test_system_candidate_requires_attempted_library_search(tmp_path: Path) -> None:
    completed = _run_preflight(
        tmp_path,
        {
            "executor_observations": _failed_executor_payload(),
            "library_search_available": True,
            "system_search_attempted": False,
            "system_candidate_found": True,
        },
    )

    assert completed.returncode == 2
    result = json.loads(completed.stderr)
    assert result["error_code"] == "invalid_host_preflight_input"
    assert result["error"] == "system_candidate_found_requires_system_search_attempted"


def test_no_executor_or_remote_observation_remains_unknown() -> None:
    decision = plan_chatgpt_host_preflight([])

    assert decision.executor_available is None
    assert decision.remote_runtime_available is None
    assert decision.remote_runtime_allowed is False


def test_explicit_negative_remote_probe_reports_false_without_enabling_route() -> None:
    decision = plan_chatgpt_host_preflight(
        [
            HostExecutorObservation(
                process_created=False,
                error_class="ClientError",
                surface="chat",
                remote_runtime_transport_available=False,
                remote_runtime_transport="public_streamable_http",
                remote_runtime_reason_code="remote_runtime_not_ready",
            )
        ]
    )

    assert decision.executor_available is False
    assert decision.remote_runtime_available is False
    assert decision.remote_runtime_allowed is False


def test_system_search_does_not_require_library_namespace_capability() -> None:
    evidence = HostDiscoveryEvidence(
        library_search_available=None,
        library_materialize_available=None,
        system_search_attempted=True,
        system_candidate_found=False,
    )

    assert evidence.library_search_available is None
    assert evidence.system_search_attempted is True
    assert evidence.system_candidate_found is False


def test_chatgpt_runbook_keeps_all_discovery_fields_tristate() -> None:
    runbook = (ROOT / "AGENTS.chatgpt.md").read_text(encoding="utf-8")

    assert "Wszystkie sześć pól są tri-state" in runbook
    assert "brak probe albo brak obserwacji pozostaje `unknown`" in runbook
    assert "nie dowodzi dostępności Biblioteki" in runbook
    assert "taki search wymaga `library_search_available=true`" not in runbook
