from __future__ import annotations

from dataclasses import dataclass


MEMORY_CONVERGE_MAX_ATTEMPTS = 3
MEMORY_CONVERGE_BACKOFF_SECONDS = (1.0, 2.0)


@dataclass(frozen=True, slots=True)
class HostOperationRetryPolicy:
    max_attempts: int
    backoff_seconds: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class HostOperationRetryDecision:
    retry_allowed: bool
    error_code: str | None
    backoff_seconds: float | None


def retry_policy_for_kind(kind: str) -> HostOperationRetryPolicy:
    normalized = str(kind or "").strip().lower()
    if normalized == "memory-converge":
        return HostOperationRetryPolicy(
            max_attempts=MEMORY_CONVERGE_MAX_ATTEMPTS,
            backoff_seconds=MEMORY_CONVERGE_BACKOFF_SECONDS,
        )
    return HostOperationRetryPolicy(max_attempts=1, backoff_seconds=())


def classify_host_operation_retry(
    *,
    kind: str,
    returncode: int,
    attempt: int,
) -> HostOperationRetryDecision:
    """Conservatively classify only explicit transient CLI results.

    memory-converge uses exit 75 for a resumable/pending convergence step. Other
    non-zero results are intentionally terminal here because the detached host
    worker must not turn integrity, permission, hash, or argument failures into
    blind retry loops.
    """

    policy = retry_policy_for_kind(kind)
    normalized = str(kind or "").strip().lower()
    code = int(returncode)

    if normalized != "memory-converge" or code != 75:
        return HostOperationRetryDecision(False, None, None)
    if attempt >= policy.max_attempts:
        return HostOperationRetryDecision(
            False,
            "memory_converge_pending_retry_exhausted",
            None,
        )

    index = max(0, min(attempt - 1, len(policy.backoff_seconds) - 1))
    backoff = policy.backoff_seconds[index] if policy.backoff_seconds else 0.0
    return HostOperationRetryDecision(
        True,
        "memory_converge_pending",
        float(backoff),
    )
