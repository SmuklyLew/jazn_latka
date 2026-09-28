from __future__ import annotations

from latka_jazn.core.host_operation_retry import (
    MEMORY_CONVERGE_MAX_ATTEMPTS,
    classify_host_operation_retry,
    retry_policy_for_kind,
)


def test_memory_converge_pending_retries_are_bounded() -> None:
    policy = retry_policy_for_kind("memory-converge")
    assert policy.max_attempts == MEMORY_CONVERGE_MAX_ATTEMPTS == 3
    assert policy.backoff_seconds == (1.0, 2.0)

    first = classify_host_operation_retry(
        kind="memory-converge",
        returncode=75,
        attempt=1,
    )
    assert first.retry_allowed is True
    assert first.error_code == "memory_converge_pending"
    assert first.backoff_seconds == 1.0

    second = classify_host_operation_retry(
        kind="memory-converge",
        returncode=75,
        attempt=2,
    )
    assert second.retry_allowed is True
    assert second.backoff_seconds == 2.0

    exhausted = classify_host_operation_retry(
        kind="memory-converge",
        returncode=75,
        attempt=3,
    )
    assert exhausted.retry_allowed is False
    assert exhausted.error_code == "memory_converge_pending_retry_exhausted"


def test_memory_converge_terminal_failure_is_never_blindly_retried() -> None:
    decision = classify_host_operation_retry(
        kind="memory-converge",
        returncode=17,
        attempt=1,
    )
    assert decision.retry_allowed is False
    assert decision.error_code is None
    assert decision.backoff_seconds is None


def test_other_host_operations_never_inherit_memory_converge_retry() -> None:
    decision = classify_host_operation_retry(
        kind="daemon-start",
        returncode=75,
        attempt=1,
    )
    assert decision.retry_allowed is False
    assert retry_policy_for_kind("daemon-start").max_attempts == 1
