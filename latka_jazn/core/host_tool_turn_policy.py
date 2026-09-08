from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Any, Mapping

from latka_jazn.version import schema_version

SCHEMA_VERSION = schema_version("host_tool_turn_policy")
KNOWN_HOST_TOOLS = frozenset({"web.run", "GitHub", "image_gen", "file_search"})


def _fold(value: str) -> str:
    return str(value or "").lower().translate(str.maketrans("ąćęłńóśźż", "acelnoszz"))


@dataclass(slots=True)
class HostToolTurnPolicy:
    allowed_tools: list[str]
    required_tools: list[str]
    max_tool_calls: int
    evidence_required_for_tools: list[str]
    host_action_evidence_required_for_tools: list[str]
    runtime_owns_turn: bool = True
    tool_results_cannot_be_voice_source: bool = True
    finalization_required_after_tool_use: bool = True
    tool_output_may_be_visible_without_runtime_finalization: bool = False
    schema_version: str = SCHEMA_VERSION
    truth_boundary: str = (
        "Narzędzia hosta są zdolnościami podporządkowanymi jednej turze runtime. "
        "Wynik web/image/GitHub/file nie staje się głosem ani tożsamością Łatki."
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_host_tool_turn_policy(
    *,
    user_text: str,
    detected_intent: str,
    route: str,
    nlg_plan: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    plan = dict(nlg_plan or {})
    folded = _fold(" ".join((user_text, detected_intent, route)))
    source_policy = str(plan.get("source_policy") or "")
    allowed: list[str] = []
    required: list[str] = []

    if source_policy == "requires_external_web" or any(token in folded for token in ("web", "sieci", "wyszuk", "research", "zrod")):
        allowed.append("web.run")
        if source_policy == "requires_external_web":
            required.append("web.run")
    if any(token in folded for token in ("github", "repo", "branch", "commit", "push", "pull request", " pr ")):
        allowed.append("GitHub")
    if any(token in folded for token in ("obraz", "grafik", "zdjec", "wygeneruj", "zobrazuj", "image")):
        allowed.append("image_gen")
    if any(token in folded for token in ("plik", "zalacz", "pdf", "dokument", "file")):
        allowed.append("file_search")

    allowed = list(dict.fromkeys(tool for tool in allowed if tool in KNOWN_HOST_TOOLS))
    required = list(dict.fromkeys(tool for tool in required if tool in allowed))
    evidence_required = [tool for tool in allowed if tool in {"web.run", "GitHub"}]
    action_evidence_required = [tool for tool in allowed if tool in {"image_gen", "file_search"}]
    max_calls = 0 if not allowed else min(8, max(1, 2 * len(allowed)))
    return HostToolTurnPolicy(
        allowed_tools=allowed,
        required_tools=required,
        max_tool_calls=max_calls,
        evidence_required_for_tools=evidence_required,
        host_action_evidence_required_for_tools=action_evidence_required,
    ).to_dict()


def validate_tool_evidence_against_policy(
    evidence: list[dict[str, Any]] | None,
    policy: Mapping[str, Any] | None,
) -> list[str]:
    contract = dict(policy or {})
    allowed = {str(item) for item in contract.get("allowed_tools") or []}
    required = {str(item) for item in contract.get("required_tools") or []}
    observed = {str(item.get("tool") or "") for item in (evidence or []) if isinstance(item, dict)}
    violations: list[str] = []
    for tool in observed:
        if tool and tool not in allowed:
            violations.append(f"tool_not_authorized_for_turn:{tool}")
    for tool in required:
        if tool not in observed:
            violations.append(f"required_tool_evidence_missing:{tool}")
    if contract.get("runtime_owns_turn") is not True:
        violations.append("runtime_turn_ownership_missing")
    if contract.get("tool_results_cannot_be_voice_source") is not True:
        violations.append("tool_voice_boundary_missing")
    return violations
