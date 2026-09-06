from __future__ import annotations

from pathlib import Path

import pytest

from latka_jazn.core.chatgpt_host_executor_contract import (
    HostCommandState,
    HostExecutorObservation,
    HostExecutorState,
    HostFilesystemState,
    HostRecoveryAction,
    classify_host_executor_observation,
)
from latka_jazn.core.chatgpt_host_recovery import plan_host_executor_recovery


ROOT = Path(__file__).resolve().parents[1]


def test_pre_process_host_failure_keeps_local_state_unknown_and_allows_one_alternative_probe() -> None:
    decision = classify_host_executor_observation(
        HostExecutorObservation(
            process_created=False,
            error_class="ClientError",
            alternative_surface_available=True,
            alternative_probe_count=0,
        )
    )

    assert decision.executor_state is HostExecutorState.HOST_EXECUTOR_UNAVAILABLE
    assert decision.command_state is HostCommandState.NOT_STARTED
    assert decision.filesystem_state is HostFilesystemState.UNKNOWN
    assert decision.package_state == "unknown"
    assert decision.runtime_state == "unverified"
    assert decision.next_action is HostRecoveryAction.PROBE_ALTERNATIVE_ONCE
    assert decision.retry_allowed is True
    assert decision.retry_budget_remaining == 1
    assert decision.canonical_resume_entrypoint is None


def test_second_pre_process_host_failure_exhausts_retry_budget_and_stops_bootstrap() -> None:
    decision = classify_host_executor_observation(
        HostExecutorObservation(
            process_created=False,
            error_class="InvalidArgumentError",
            alternative_surface_available=True,
            alternative_probe_count=1,
        )
    )

    assert decision.executor_state is HostExecutorState.HOST_EXECUTOR_UNAVAILABLE
    assert decision.next_action is HostRecoveryAction.STOP_LOCAL_BOOTSTRAP
    assert decision.retry_allowed is False
    assert decision.retry_budget_remaining == 0
    assert decision.filesystem_state is HostFilesystemState.UNKNOWN
    assert decision.package_state == "unknown"
    assert decision.runtime_state == "unverified"


def test_started_local_process_with_nonzero_returncode_is_not_host_executor_failure() -> None:
    decision = classify_host_executor_observation(
        HostExecutorObservation(
            process_created=True,
            command_completed=True,
            returncode=2,
            error_class="CalledProcessError",
            filesystem_probe_succeeded=False,
        )
    )

    assert decision.executor_state is HostExecutorState.AVAILABLE
    assert decision.command_state is HostCommandState.FAILED
    assert decision.next_action is HostRecoveryAction.DIAGNOSE_LOCAL_COMMAND
    assert decision.reason_code == "local_command_returned_nonzero"
    assert decision.retry_allowed is False
    assert decision.canonical_resume_entrypoint is None


def test_successful_filesystem_preflight_resumes_only_canonical_discovery() -> None:
    decision = classify_host_executor_observation(
        HostExecutorObservation(
            process_created=True,
            command_completed=True,
            returncode=0,
            filesystem_probe_succeeded=True,
        )
    )

    assert decision.executor_state is HostExecutorState.AVAILABLE
    assert decision.command_state is HostCommandState.SUCCEEDED
    assert decision.filesystem_state is HostFilesystemState.OBSERVED
    assert decision.package_state == "unknown"
    assert decision.runtime_state == "unverified"
    assert decision.next_action is HostRecoveryAction.RESUME_CANONICAL_DISCOVERY
    assert decision.canonical_resume_entrypoint == "run.py"


def test_started_but_unfinished_process_is_diagnosed_as_local_process_state() -> None:
    decision = classify_host_executor_observation(
        HostExecutorObservation(process_created=True)
    )

    assert decision.executor_state is HostExecutorState.AVAILABLE
    assert decision.command_state is HostCommandState.STARTED_UNFINISHED
    assert decision.next_action is HostRecoveryAction.DIAGNOSE_LOCAL_COMMAND
    assert decision.reason_code == "local_process_started_without_completed_command"


def test_observation_rejects_impossible_state_combinations() -> None:
    with pytest.raises(ValueError, match="command_completed_requires_process_created"):
        HostExecutorObservation(process_created=False, command_completed=True)

    with pytest.raises(ValueError, match="returncode_requires_completed_command"):
        HostExecutorObservation(process_created=True, returncode=0)

    with pytest.raises(ValueError, match="filesystem_probe_result_requires_completed_command"):
        HostExecutorObservation(
            process_created=True,
            filesystem_probe_succeeded=True,
        )


def test_chatgpt_host_recovery_module_exposes_same_fail_closed_contract() -> None:
    decision = plan_host_executor_recovery(
        HostExecutorObservation(
            process_created=False,
            error_class="ClientError",
            alternative_surface_available=False,
        )
    )

    payload = decision.to_dict()
    assert payload["executor_state"] == "host_executor_unavailable"
    assert payload["filesystem_state"] == "unknown"
    assert payload["package_state"] == "unknown"
    assert payload["runtime_state"] == "unverified"
    assert payload["next_action"] == "stop_local_bootstrap"
    assert payload["canonical_resume_entrypoint"] is None


def test_project_loader_documents_bounded_recovery_and_external_support_boundary() -> None:
    instructions_path = ROOT / "docs" / "runtime" / "CHATGPT_PROJECT_INSTRUCTIONS.txt"
    text = instructions_path.read_text(encoding="utf-8")

    assert len(text) <= 8000
    assert "host_executor_unavailable" in text
    assert "najwyżej jedną próbę" in text
    assert "przed utworzeniem procesu" in text
    assert "niezerowy kod wyjścia" in text
    assert "run.py" in text
    assert "status.openai.com" in text
    assert "HAR" in text
    assert "Nie zapisuj HAR" in text
