from __future__ import annotations

import pytest

from latka_jazn.core.chatgpt_host_executor_aggregate_helpers import surface_payload
from latka_jazn.core.chatgpt_host_executor_contract import (
    HostExecutionRoute,
    HostExecutorObservation,
    HostExecutorState,
    HostFilesystemState,
    HostRecoveryAction,
    aggregate_host_executor_observations,
    classify_host_executor_observation,
)
from latka_jazn.core.chatgpt_host_executor_failure_codes import classify_prespan_error


@pytest.mark.parametrize(
    "raw",
    [
        "ClientError",
        "caas.internal.errors.ClientError",
        "<class 'caas.internal.errors.ClientError'>",
        ' <class "caas.internal.errors.ClientError">. ',
        "Encountered exception: <class 'caas.internal.errors.ClientError'>.",
        "ClientError\\nEncountered exception: <class 'caas.internal.errors.ClientError'>.",
    ],
)
def test_caas_client_error_formats_map_to_same_failure_policy(raw: str) -> None:
    policy = classify_prespan_error(raw)
    assert policy.reason_code == "host_client_error_pre_spawn"
    assert policy.retry_class == "ambiguous_host_failure"
    assert policy.same_request_retry_allowed is False
    assert policy.switch_surface_preferred is True


@pytest.mark.parametrize(
    "raw",
    [
        "ClientErrorX",
        "Request failed because of ClientError",
        "ValueError: ClientError",
        "ClientError\\nEncountered exception: <class 'caas.internal.errors.InvalidArgumentError'>.",
        "<class 'caas.internal.errors.ClientError'> user text",
        "Encountered exception: <class 'caas.internal.errors.ClientError'>. extra",
    ],
)
def test_unknown_and_conflicting_strings_fail_closed(raw: str) -> None:
    assert classify_prespan_error(raw).reason_code == "host_unknown_error_pre_spawn"


def test_message_only_exact_signature_is_recognized_before_spawn() -> None:
    observation = HostExecutorObservation(
        process_created=False,
        error_class=None,
        error_message="Encountered exception: <class 'caas.internal.errors.ClientError'>.",
        alternative_surface_available=True,
    )
    decision = classify_host_executor_observation(observation)
    payload = surface_payload(observation, decision)
    assert decision.executor_state is HostExecutorState.HOST_EXECUTOR_UNAVAILABLE
    assert decision.next_action is HostRecoveryAction.PROBE_ALTERNATIVE_ONCE
    assert decision.retry_budget_remaining == 1
    assert decision.reason_code == "host_client_error_pre_spawn"
    assert decision.filesystem_state is HostFilesystemState.UNKNOWN
    assert decision.package_state == "unknown"
    assert decision.runtime_state == "unverified"
    assert payload["normalized_reason_code"] == "host_client_error_pre_spawn"
    assert payload["switch_surface_preferred"] is True
    assert payload["same_request_retry_allowed"] is False


def test_arbitrary_message_without_error_class_does_not_claim_failure() -> None:
    obs = HostExecutorObservation(process_created=False, error_message="ClientError in copied user text")
    decision = classify_host_executor_observation(obs)
    assert decision.executor_state is HostExecutorState.UNKNOWN
    assert surface_payload(obs, decision)["normalized_reason_code"] is None


def test_retry_budget_and_no_replay_after_both_surfaces_fail() -> None:
    first = HostExecutorObservation(
        process_created=False,
        error_class="caas.internal.errors.ClientError",
        surface="primary",
        alternative_surface_available=True,
        alternative_probe_count=0,
    )
    second = HostExecutorObservation(
        process_created=False,
        error_class="<class 'caas.internal.errors.ClientError'>",
        surface="alternative",
        alternative_surface_available=False,
        alternative_probe_count=1,
    )
    assert classify_host_executor_observation(first).next_action is HostRecoveryAction.PROBE_ALTERNATIVE_ONCE
    final = classify_host_executor_observation(second)
    assert final.next_action is HostRecoveryAction.STOP_LOCAL_BOOTSTRAP
    assert final.retry_allowed is False
    assert final.retry_budget_remaining == 0
    aggregate = aggregate_host_executor_observations((first, second))
    assert aggregate.execution_route is HostExecutionRoute.NONE or aggregate.execution_route.value == "none"


def test_independent_success_overrules_previous_host_clienterror() -> None:
    first = HostExecutorObservation(
        process_created=False,
        error_class="caas.internal.errors.ClientError",
        surface="primary",
    )
    alternate = HostExecutorObservation(
        process_created=True,
        command_completed=True,
        returncode=0,
        filesystem_probe_succeeded=True,
        surface="independent",
    )
    aggregate = aggregate_host_executor_observations((first, alternate))
    assert aggregate.execution_route is HostExecutionRoute.LOCAL_EXECUTOR or aggregate.execution_route.value == "local_executor"
    assert aggregate.canonical_resume_entrypoint == "run.py" or aggregate.canonical_resume_entrypoint is None


def test_started_process_is_not_mislabeled_a_prespan_error() -> None:
    obs = HostExecutorObservation(
        process_created=True,
        error_class="caas.internal.errors.ClientError",
        command_completed=False,
    )
    decision = classify_host_executor_observation(obs)
    assert decision.executor_state is HostExecutorState.AVAILABLE
    assert surface_payload(obs, decision)["normalized_reason_code"] is None
