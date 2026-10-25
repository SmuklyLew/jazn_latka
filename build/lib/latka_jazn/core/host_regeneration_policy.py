from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable

from latka_jazn.version import schema_version


SCHEMA_VERSION = schema_version("host_regeneration_policy")
REGENERABLE_VIOLATIONS = frozenset({
    "forbidden_host_voice_prefix",
    "malformed_message_envelope",
    # One bounded rewrite is safe; the candidate still passes the full,
    # unchanged truth, memory and finalization gates on resubmission.
    "memory_claim_without_allowed_memory_payload",
    "memory_claim_without_grounded_items",
    "self_state_question_missing_operational_state",
    "missing_required_components_for_intent",
    "compound_component_coverage_incomplete",
})


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
    if allowed:
        if codes == ["forbidden_host_voice_prefix"]:
            reason = "forbidden_host_voice_prefix_retry"
        elif codes == ["malformed_message_envelope"]:
            reason = "malformed_message_envelope_retry"
        elif set(codes).issubset({"forbidden_host_voice_prefix", "malformed_message_envelope"}):
            reason = "host_visible_format_retry"
        else:
            reason = "host_candidate_semantic_retry"
    elif safe:
        reason = "regeneration_budget_exhausted"
    else:
        reason = "non_regenerable_finalization_violation"
    return HostRegenerationDecision(
        regenerate=allowed,
        reason=reason,
        attempt=int(attempts_used) + (1 if allowed else 0),
        max_attempts=int(max_attempts),
        violations=codes,
    )
