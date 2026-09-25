from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class HostDiscoveryEvidence:
    """Host-reported evidence for logical SYSTEM discovery capabilities.

    ``None`` means the host did not report enough evidence to classify the
    capability or outcome. ``False`` is therefore reserved for an explicit
    negative observation, which keeps fail-closed diagnostics distinguishable
    from an unobserved capability. ``library_*`` fields describe the ChatGPT
    Library namespace specifically, while ``system_search_*`` describes a
    SYSTEM lookup on any logical host file surface (conversation, Project,
    Library, or an equivalent capability). A SYSTEM search therefore does not
    imply that Library itself was available. Executor and remote-runtime
    availability are derived elsewhere from verified runtime observations and
    are not trusted from this host-reported structure.
    """

    library_search_available: bool | None = None
    library_materialize_available: bool | None = None
    system_search_attempted: bool | None = None
    system_candidate_found: bool | None = None

    def __post_init__(self) -> None:
        if self.system_candidate_found is True and self.system_search_attempted is not True:
            raise ValueError(
                "system_candidate_found_requires_system_search_attempted"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "library_search_available": self.library_search_available,
            "library_materialize_available": self.library_materialize_available,
            "system_search_attempted": self.system_search_attempted,
            "system_candidate_found": self.system_candidate_found,
        }


def discovery_evidence_from_payload(payload: Mapping[str, Any]) -> HostDiscoveryEvidence:
    def tri_state(key: str) -> bool | None:
        if key not in payload or payload[key] is None:
            return None
        value = payload[key]
        if not isinstance(value, bool):
            raise ValueError(f"{key}_must_be_boolean_or_null")
        return value

    return HostDiscoveryEvidence(
        library_search_available=tri_state("library_search_available"),
        library_materialize_available=tri_state("library_materialize_available"),
        system_search_attempted=tri_state("system_search_attempted"),
        system_candidate_found=tri_state("system_candidate_found"),
    )
