from __future__ import annotations

"""Truthful bootstrap progress model for ChatGPT-hosted Jaźń startup.

The model reports only completed, evidence-backed gates. It deliberately keeps
SYSTEM wake readiness separate from optional MEMORY attachment so a missing
optional memory package never turns a ready core into a fake "99%" state.
"""

from dataclasses import asdict, dataclass
from typing import Iterable

from latka_jazn.version import schema_version

SCHEMA_VERSION = schema_version("chatgpt_bootstrap_progress")

CORE_GATE_MILESTONES: tuple[tuple[str, int], ...] = (
    ("executor_probe", 5),
    ("system_package_verified", 15),
    ("zip_validated", 30),
    ("operator_materialized", 55),
    ("host_preflight", 65),
    ("contracts_loaded", 72),
    ("daemon_started", 82),
    ("live_readiness", 95),
    ("turn_channel_bound", 100),
)

_CORE_PERCENT_BY_GATE = dict(CORE_GATE_MILESTONES)
_VALID_MEMORY_MODES = frozenset({"off", "optional", "required"})


@dataclass(frozen=True, slots=True)
class ChatGptBootstrapProgress:
    schema_version: str
    phase: str
    status: str
    core_wake_percent: int
    configured_ready_percent: int
    completed_gates: tuple[str, ...]
    next_gate: str | None
    memory_mode: str
    memory_state: str
    memory_percent: int | None
    truth_boundary: str

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["completed_gates"] = list(self.completed_gates)
        return payload


def _normalized_memory_mode(value: str | None) -> str:
    mode = str(value or "optional").strip().lower()
    return mode if mode in _VALID_MEMORY_MODES else "optional"


def _core_percent(completed_gates: Iterable[str]) -> tuple[int, tuple[str, ...]]:
    completed_set = set(completed_gates)
    completed = tuple(
        gate for gate, _percent in CORE_GATE_MILESTONES if gate in completed_set
    )
    if not completed:
        return 0, ()
    return max(_CORE_PERCENT_BY_GATE[gate] for gate in completed), completed


def _next_gate(completed: tuple[str, ...]) -> str | None:
    completed_set = set(completed)
    for gate, _percent in CORE_GATE_MILESTONES:
        if gate not in completed_set:
            return gate
    return None


def build_chatgpt_bootstrap_progress(
    *,
    phase: str,
    completed_gates: Iterable[str],
    status: str = "in_progress",
    memory_mode: str = "optional",
    memory_state: str = "not_attached",
    memory_percent: int | None = None,
) -> ChatGptBootstrapProgress:
    """Build a progress snapshot without inventing work that has not completed."""

    core_percent, completed = _core_percent(completed_gates)
    mode = _normalized_memory_mode(memory_mode)

    normalized_memory_percent: int | None
    if memory_percent is None:
        normalized_memory_percent = None
    else:
        normalized_memory_percent = max(0, min(100, int(memory_percent)))

    if mode == "required":
        # Persistent MEMORY is a separate required readiness dimension. Core
        # wake progress remains truthful and reaches 100 independently, while
        # configured readiness reserves 15% for the required memory gate.
        mem = normalized_memory_percent or 0
        configured = round((core_percent * 0.85) + (mem * 0.15))
    else:
        configured = core_percent

    return ChatGptBootstrapProgress(
        schema_version=SCHEMA_VERSION,
        phase=str(phase or "unknown"),
        status=str(status or "in_progress"),
        core_wake_percent=core_percent,
        configured_ready_percent=max(0, min(100, configured)),
        completed_gates=completed,
        next_gate=_next_gate(completed),
        memory_mode=mode,
        memory_state=str(memory_state or "unknown"),
        memory_percent=normalized_memory_percent,
        truth_boundary=(
            "Percentages are milestone-derived from completed gates only. "
            "Optional MEMORY never blocks SYSTEM wake readiness; required MEMORY "
            "is reported as a separate readiness dimension and cannot be inferred "
            "from SYSTEM/package state."
        ),
    )


__all__ = [
    "CORE_GATE_MILESTONES",
    "ChatGptBootstrapProgress",
    "build_chatgpt_bootstrap_progress",
]
