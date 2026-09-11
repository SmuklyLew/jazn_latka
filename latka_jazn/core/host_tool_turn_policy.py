from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Any, Mapping

from latka_jazn.core.host_media_resources import detect_media_lookup
from latka_jazn.core.host_tool_capabilities import (
    build_host_tool_capability_snapshot,
    resolve_policy_tool_availability,
)
from latka_jazn.version import schema_version

SCHEMA_VERSION = schema_version("host_tool_turn_policy")
_URL_RE = re.compile(r"(?:https?://|www\.)\S+", flags=re.IGNORECASE)


def _fold(value: str) -> str:
    return str(value or "").lower().translate(str.maketrans("ąćęłńóśźż", "acelnoszz"))


@dataclass(slots=True)
class HostToolTurnPolicy:
    requested_tools: list[str]
    allowed_tools: list[str]
    required_tools: list[str]
    required_tools_unavailable: list[str]
    capability_confirmation_required_for_tools: list[str]
    max_tool_calls: int
    evidence_required_for_tools: list[str]
    host_action_evidence_required_for_tools: list[str]
    tool_availability_basis: str
    host_tool_capability_status: str | None
    host_tool_capability_manifest_source: str | None
    media_lookup_signal: dict[str, Any]
    runtime_owns_turn: bool = True
    tool_results_cannot_be_voice_source: bool = True
    finalization_required_after_tool_use: bool = True
    tool_output_may_be_visible_without_runtime_finalization: bool = False
    tool_result_is_intermediate: bool = True
    same_turn_resume_required: bool = True
    accepted_visible_turn_required: bool = True
    message_envelope_required: bool = True
    host_must_report_probe_evidence: bool = True
    schema_version: str = SCHEMA_VERSION
    truth_boundary: str = (
        "Narzędzia hosta są zdolnościami podporządkowanymi jednej turze runtime. "
        "Dostępność narzędzia pochodzi z hostowego manifestu lub zweryfikowanego evidence, nie z TTY, PID ani importu. "
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
    host_tool_capabilities: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    plan = dict(nlg_plan or {})
    folded = _fold(" ".join((user_text, detected_intent, route)))
    source_policy = str(plan.get("source_policy") or "")
    requested: list[str] = []
    required_requested: list[str] = []
    user_has_url = bool(_URL_RE.search(str(user_text or "")))
    media_lookup_signal = detect_media_lookup(user_text)
    media_lookup = media_lookup_signal.get("media_lookup") is True

    if (
        source_policy == "requires_external_web"
        or user_has_url
        or media_lookup
        or any(token in folded for token in ("web", "sieci", "wyszuk", "research", "zrod"))
    ):
        requested.append("web.run")
        if source_policy == "requires_external_web" or user_has_url:
            required_requested.append("web.run")
    if any(token in folded for token in ("github", "repo", "branch", "commit", "push", "pull request", " pr ")):
        requested.append("GitHub")
    if any(token in folded for token in ("obraz", "grafik", "zdjec", "wygeneruj", "zobrazuj", "image")):
        requested.append("image_gen")
    if any(token in folded for token in ("plik", "zalacz", "pdf", "dokument", "file")):
        requested.append("file_search")
    if any(token in folded for token in ("przypomn", "reminder", "harmonogram", "schedule", "co godzin", "codziennie")):
        requested.append("automations")

    requested = list(dict.fromkeys(requested))
    required_requested = list(dict.fromkeys(required_requested))
    capability_snapshot = dict(host_tool_capabilities or build_host_tool_capability_snapshot())
    availability = resolve_policy_tool_availability(requested, snapshot=capability_snapshot)
    allowed = list(availability.get("allowed_tools") or [])
    required = [tool for tool in required_requested if tool in allowed]
    required_unavailable = [tool for tool in required_requested if tool not in allowed]
    confirmation_required = list(availability.get("capability_confirmation_required_for_tools") or [])
    evidence_required = [tool for tool in allowed if tool in {"web.run", "GitHub"}]
    action_evidence_required = [
        tool
        for tool in allowed
        if tool in {"image_gen", "file_search", "automations", "python_user_visible"}
    ]
    max_calls = 0 if not allowed else min(8, max(1, 2 * len(allowed)))
    return HostToolTurnPolicy(
        requested_tools=list(availability.get("requested_tools") or requested),
        allowed_tools=allowed,
        required_tools=required,
        required_tools_unavailable=required_unavailable,
        capability_confirmation_required_for_tools=confirmation_required,
        max_tool_calls=max_calls,
        evidence_required_for_tools=evidence_required,
        host_action_evidence_required_for_tools=action_evidence_required,
        tool_availability_basis=str(availability.get("availability_basis") or "unknown"),
        host_tool_capability_status=(
            str(availability.get("snapshot_status")) if availability.get("snapshot_status") is not None else None
        ),
        host_tool_capability_manifest_source=(
            str(availability.get("manifest_source")) if availability.get("manifest_source") is not None else None
        ),
        media_lookup_signal=media_lookup_signal,
    ).to_dict()


def validate_tool_evidence_against_policy(
    evidence: list[dict[str, Any]] | None,
    policy: Mapping[str, Any] | None,
) -> list[str]:
    contract = dict(policy or {})
    allowed = {str(item) for item in contract.get("allowed_tools") or []}
    required = {str(item) for item in contract.get("required_tools") or []}
    required_unavailable = {str(item) for item in contract.get("required_tools_unavailable") or []}
    observed = {str(item.get("tool") or "") for item in (evidence or []) if isinstance(item, dict)}
    violations: list[str] = []
    for tool in observed:
        if tool and tool not in allowed:
            violations.append(f"tool_not_authorized_for_turn:{tool}")
    for tool in required:
        if tool not in observed:
            violations.append(f"required_tool_evidence_missing:{tool}")
    for tool in required_unavailable:
        violations.append(f"required_host_tool_unavailable:{tool}")
    if contract.get("runtime_owns_turn") is not True:
        violations.append("runtime_turn_ownership_missing")
    if contract.get("tool_results_cannot_be_voice_source") is not True:
        violations.append("tool_voice_boundary_missing")
    if observed and contract.get("finalization_required_after_tool_use") is not True:
        violations.append("tool_finalization_requirement_missing")
    if observed and contract.get("same_turn_resume_required") is not True:
        violations.append("tool_same_turn_resume_requirement_missing")
    if observed and contract.get("tool_output_may_be_visible_without_runtime_finalization") is not False:
        violations.append("tool_output_visibility_boundary_missing")
    if observed and contract.get("accepted_visible_turn_required") is not True:
        violations.append("accepted_visible_turn_requirement_missing")
    if observed and contract.get("message_envelope_required") is not True:
        violations.append("message_envelope_requirement_missing")
    return violations
