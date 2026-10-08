from __future__ import annotations

from dataclasses import dataclass
import re


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


_CLASS_PATH = r"[A-Za-z_][A-Za-z_0-9]*(?:\.[A-Za-z_][A-Za-z_0-9]*)*"
_QUALIFIED_EXCEPTION_RE = re.compile(_CLASS_PATH)
_PYTHON_CLASS_REPR = re.compile(
    r"""<class\s+(?P<quote>['"])(?P<name>""" + _CLASS_PATH + r""")(?P=quote)>\.?"""
)


def _parse_exception_identifier(value: str) -> str | None:
    """Accept only an entire identifier or Python exception class repr, never substrings."""

    raw = value.strip()
    if raw.startswith("Encountered exception:"):
        raw = raw[len("Encountered exception:"):].strip()
    match = _PYTHON_CLASS_REPR.fullmatch(raw)
    if match:
        raw = match.group("name")
    elif not _QUALIFIED_EXCEPTION_RE.fullmatch(raw):
        return None
    return raw.rsplit(".", 1)[-1].casefold()


def _normalize_exception_identifier(value: str | None) -> str | None:
    raw = str(value or "").strip()
    if not raw or len(raw) > 1024:
        return None
    # A host may supply the two-line diagnostic itself in error_class. Require
    # the class name on both sides to agree, rather than substring-matching.
    if "Encountered exception:" in raw and not raw.startswith("Encountered exception:"):
        first, second = raw.split("Encountered exception:", 1)
        left = _parse_exception_identifier(first)
        right = _parse_exception_identifier("Encountered exception:" + second)
        return left if left and left == right else None
    return _parse_exception_identifier(raw)


def classify_prespan_error(
    error_class: str | None, *, error_message: str | None = None
) -> PreSpawnFailurePolicy:
    """Classify bounded host exception evidence; never grant execution capability.

    Prefer the explicit class field. A missing class may be recovered only from
    an exact, known Python exception signature, not arbitrary message content.
    This describes a failure BEFORE process creation only; callers must check
    process_created separately. The host owns the alternative-probe budget and
    request idempotency, not this classifier.
    """

    key = _normalize_exception_identifier(error_class)
    if key is None and not error_class:
        key = _normalize_exception_identifier(error_message)
    return _PRESPAWN_FAILURE_POLICIES.get(key or "", _DEFAULT_POLICY)
