from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable

from latka_jazn.version import schema_version


SCHEMA_VERSION = schema_version("host_regeneration_policy")
REGENERABLE_VIOLATIONS = frozenset({"forbidden_host_voice_prefix"})


@dataclass(slots=True)
class HostRegenerationDecision:
    regenerate: bool
    reason: str
    attempt: int
    max_attempts: int
    violations: list[str]
    schema_version: str = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def decide_host_regeneration(
    violations: Iterable[str],
    *,
    attempts_used: int,
    max_attempts: int = 1,
) -> HostRegenerationDecision:
    codes = list(dict.fromkeys(str(item) for item in violations if str(item)))
    safe = bool(codes) and set(codes).issubset(REGENERABLE_VIOLATIONS)
    allowed = safe and int(attempts_used) < int(max_attempts)
    reason = (
        "forbidden_host_voice_prefix_retry"
        if allowed
        else "regeneration_budget_exhausted"
        if safe
        else "non_regenerable_finalization_violation"
    )
    return HostRegenerationDecision(
        regenerate=allowed,
        reason=reason,
        attempt=int(attempts_used) + (1 if allowed else 0),
        max_attempts=int(max_attempts),
        violations=codes,
    )
