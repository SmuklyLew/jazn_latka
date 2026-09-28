from __future__ import annotations

import pytest

from latka_jazn.core.chatgpt_host_executor_aggregate_helpers import surface_payload
from latka_jazn.core.chatgpt_host_executor_contract import (
    HostExecutorObservation,
    HostFilesystemState,
    classify_host_executor_observation,
)
from latka_jazn.core.chatgpt_host_executor_failure_codes import classify_prespan_error


@pytest.mark.parametrize(
    ("error_class", "reason_code", "retry_class", "same_request_retry", "switch_surface"),
    [
        (
            "ClientError",
            "host_client_error_pre_spawn",
            "ambiguous_host_failure",
            False,
            True,
        ),
        (
            "InvalidArgumentError",
            "host_invalid_argument_pre_spawn",
            "non_retryable_request",
            False,
            False,
        ),
        (
            "TransportTimeoutError",
            "host_transport_timeout_pre_spawn",
            "transient_transport",
            True,
            False,
        ),
        (
            "StreamingExecNotEnabledContainerError",
            "host_streaming_exec_unavailable_pre_spawn",
            "unsupported_surface",
            False,
            True,
        ),
    ],
)
def test_pre_spawn_failures_receive_stable_semantics(
    error_class: str,
    reason_code: str,
    retry_class: str,
    same_request_retry: bool,
    switch_surface: bool,
) -> None:
    policy = classify_prespan_error(error_class)
    assert policy.reason_code == reason_code
    assert policy.retry_class == retry_class
    assert policy.same_request_retry_allowed is same_request_retry
    assert policy.switch_surface_preferred is switch_surface

    observation = HostExecutorObservation(
        process_created=False,
        error_class=error_class,
        spawn_phase="allocation",
        intended_cwd="/mnt/data/jazn_runtime",
        executor_allocation_state=False,
        materialization_state=None,
        mount_preparation_state=None,
    )
    decision = classify_host_executor_observation(observation)

    assert decision.reason_code == reason_code
    assert decision.filesystem_state is HostFilesystemState.UNKNOWN
    assert decision.package_state == "unknown"
    assert decision.runtime_state == "unverified"

    payload = surface_payload(observation, decision)
    assert payload["normalized_reason_code"] == reason_code
    assert payload["retry_class"] == retry_class
    assert payload["same_request_retry_allowed"] is same_request_retry
    assert payload["switch_surface_preferred"] is switch_surface
    assert payload["spawn_phase"] == "allocation"
    assert payload["intended_cwd"] == "/mnt/data/jazn_runtime"
    assert payload["pid"] is None


def test_client_error_before_spawn_never_claims_filesystem_failure() -> None:
    observation = HostExecutorObservation(
        process_created=False,
        error_class="ClientError",
        error_code="executor_allocation_failed",
        spawn_phase="allocation",
        executor_allocation_state=False,
    )
    decision = classify_host_executor_observation(observation)
    payload = surface_payload(observation, decision)

    assert decision.reason_code == "host_client_error_pre_spawn"
    assert payload["process_created"] is False
    assert payload["executor_allocation_state"] is False
    assert payload["materialization_state"] is None
    assert payload["mount_preparation_state"] is None
    assert decision.filesystem_state.value == "unknown"
    assert decision.package_state == "unknown"
    assert decision.runtime_state == "unverified"


def test_unknown_error_remains_fail_closed() -> None:
    observation = HostExecutorObservation(
        process_created=False,
        error_class="ProviderSpecificFailure",
    )
    decision = classify_host_executor_observation(observation)
    assert decision.reason_code == "host_unknown_error_pre_spawn"
    assert decision.retry_allowed is False


def test_process_evidence_is_forbidden_before_spawn() -> None:
    with pytest.raises(ValueError, match="pid_requires_process_created"):
        HostExecutorObservation(
            process_created=False,
            error_class="ClientError",
            pid=123,
        )

    with pytest.raises(ValueError, match="observed_cwd_requires_process_created"):
        HostExecutorObservation(
            process_created=False,
            error_class="ClientError",
            observed_cwd="/tmp/runtime",
        )


def test_command_fingerprint_must_be_sha256() -> None:
    with pytest.raises(ValueError, match="command_fingerprint_sha256_must_be_64_hex"):
        HostExecutorObservation(
            process_created=False,
            error_class="ClientError",
            command_fingerprint_sha256="not-a-digest",
        )


def test_post_spawn_evidence_is_exported_without_changing_command_truth() -> None:
    observation = HostExecutorObservation(
        process_created=True,
        command_completed=False,
        pid=321,
        observed_cwd="/opt/jazn",
        platform="linux",
        effective_uid=1000,
        effective_gid=1000,
        spawn_phase="spawned",
        command_fingerprint_sha256="a" * 64,
    )
    decision = classify_host_executor_observation(observation)
    payload = surface_payload(observation, decision)

    assert payload["pid"] == 321
    assert payload["observed_cwd"] == "/opt/jazn"
    assert payload["platform"] == "linux"
    assert payload["effective_uid"] == 1000
    assert payload["effective_gid"] == 1000
    assert payload["normalized_reason_code"] is None
