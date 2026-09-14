from __future__ import annotations

from enum import Enum


class HostHandoffState(str, Enum):
    """Observed consent/lifecycle state for a host execution handoff."""

    UNKNOWN = "unknown"
    UNAVAILABLE = "unavailable"
    AVAILABLE = "available"
    REQUESTED = "requested"
    ACCEPTED = "accepted"
    DECLINED = "declined"


HANDOFF_ACTIVE_STATES = frozenset({
    HostHandoffState.AVAILABLE,
    HostHandoffState.REQUESTED,
    HostHandoffState.ACCEPTED,
    HostHandoffState.DECLINED,
})


def normalize_handoff_state(value: HostHandoffState | str) -> HostHandoffState:
    if isinstance(value, HostHandoffState):
        return value
    try:
        return HostHandoffState(str(value or "").strip().lower())
    except ValueError as exc:
        raise ValueError(f"invalid_execution_handoff_state:{value!r}") from exc
