from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PreSpawnFailurePolicy:
    """Stable host-side classification for failures observed before process creation.

    This classification is descriptive evidence only. It does not grant the host
    permission to loop or replay a request. Recovery budgets remain owned by the
    canonical host executor policy.
    """

    reason_code: str
    retry_class: str
    same_request_retry_allowed: bool
    switch_surface_preferred: bool


_DEFAULT_POLICY = PreSpawnFailurePolicy(
    reason_code="host_unknown_error_pre_spawn",
    retry_class="unknown",
    same_request_retry_allowed=False,
    switch_surface_preferred=False,
)

_PRESPAWN_FAILURE_POLICIES: dict[str, PreSpawnFailurePolicy] = {
    "clienterror": PreSpawnFailurePolicy(
        reason_code="host_client_error_pre_spawn",
        retry_class="ambiguous_host_failure",
        same_request_retry_allowed=False,
        switch_surface_preferred=True,
    ),
    "invalidargumenterror": PreSpawnFailurePolicy(
        reason_code="host_invalid_argument_pre_spawn",
        retry_class="non_retryable_request",
        same_request_retry_allowed=False,
        switch_surface_preferred=False,
    ),
    "transporttimeouterror": PreSpawnFailurePolicy(
        reason_code="host_transport_timeout_pre_spawn",
        retry_class="transient_transport",
        same_request_retry_allowed=True,
        switch_surface_preferred=False,
    ),
    "streamingexecnotenabledcontainererror": PreSpawnFailurePolicy(
        reason_code="host_streaming_exec_unavailable_pre_spawn",
        retry_class="unsupported_surface",
        same_request_retry_allowed=False,
        switch_surface_preferred=True,
    ),
}


def classify_prespan_error(error_class: str | None) -> PreSpawnFailurePolicy:
    """Map host error classes to stable pre-spawn semantics.

    Unknown classes remain fail-closed. In particular, this function never
    claims anything about filesystem, package, MEMORY, SQLite, or runtime state.
    """

    key = str(error_class or "").strip().casefold()
    return _PRESPAWN_FAILURE_POLICIES.get(key, _DEFAULT_POLICY)
