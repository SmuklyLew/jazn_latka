from __future__ import annotations

from dataclasses import asdict, dataclass, field
import re
from typing import Any, Mapping

from latka_jazn.version import schema_version

SCHEMA_VERSION = schema_version("reasoning_orchestrator")


@dataclass(slots=True)
class ReasoningPlan:
    mode: str
    complexity_score: float
    uncertainty_score: float
    requires_retrieval: bool
    requires_tools: bool
    requires_verification: bool
    consider_alternatives: bool
    operational_steps: list[str] = field(default_factory=list)
    stop_conditions: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    schema_version: str = SCHEMA_VERSION
    truth_boundary: str = (
        "Plan zawiera wyłącznie jawne kroki operacyjne i bramki weryfikacji. "
        "Nie zapisuje ani nie ujawnia prywatnego toku rozumowania modelu."
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ReasoningOrchestrator:
    """Select an economical reasoning lane and an auditable operational plan."""

    _RETRIEVAL_INTENTS = (
        "memory", "recall", "research", "dictionary", "source", "archive", "knowledge",
    )
    _TOOL_INTENTS = ("execution", "update", "repair", "research", "file", "audit")
    _HIGH_RISK_MARKERS = (
        "sprawdz", "zweryfik", "dokladnie", "bez bled", "nie popeln", "pelny", "wszystko",
        "master", "commit", "push", "merge", "usun", "nadpis",
    )
    _COMPLEXITY_MARKERS = (
        "najpierw", "nastepnie", "potem", "oraz", "jednoczesnie", "krok po kroku",
        "architektur", "projekt", "porown", "przeanaliz", "rozbud", "zaplanuj",
    )

    @staticmethod
    def _fold(text: str) -> str:
        return re.sub(r"\s+", " ", str(text or "").lower()).translate(
            str.maketrans("ąćęłńóśźż", "acelnoszz")
        ).strip()

    def plan(
        self,
        *,
        user_text: str,
        intent: str,
        route: str | None = None,
        task_state: Mapping[str, Any] | None = None,
        classifier_confidence: float | None = None,
        source_available: bool = False,
        tool_available: bool = False,
    ) -> ReasoningPlan:
        folded = self._fold(user_text)
        intent_folded = self._fold(intent)
        words = [item for item in folded.split() if item]
        evidence: list[str] = []

        length_component = min(0.35, len(words) / 120.0)
        structure_component = min(0.35, 0.07 * sum(marker in folded for marker in self._COMPLEXITY_MARKERS))
        task_component = 0.20 if any(marker in intent_folded for marker in ("update", "audit", "architecture", "research", "recall")) else 0.0
        complexity = min(1.0, 0.10 + length_component + structure_component + task_component)

        confidence = 0.65 if classifier_confidence is None else max(0.0, min(1.0, float(classifier_confidence)))
        uncertainty = max(0.0, min(1.0, 1.0 - confidence))
        if task_state and bool(task_state.get("active")):
            uncertainty = max(0.0, uncertainty - 0.08)
            evidence.append("structured active task reduces intent ambiguity")

        requires_retrieval = any(marker in intent_folded for marker in self._RETRIEVAL_INTENTS)
        requires_tools = any(marker in intent_folded for marker in self._TOOL_INTENTS)
        verification_marked = any(marker in folded for marker in self._HIGH_RISK_MARKERS)
        requires_verification = verification_marked or requires_tools or complexity >= 0.58
        consider_alternatives = complexity >= 0.72 or uncertainty >= 0.34

        if complexity < 0.38 and uncertainty < 0.28 and not requires_tools:
            mode = "fast"
        elif complexity >= 0.68 or uncertainty >= 0.34 or requires_tools:
            mode = "deliberative"
        else:
            mode = "standard"

        steps = ["understand_current_goal"]
        if task_state and bool(task_state.get("active")):
            steps.append("bind_active_dialogue_task")
        if requires_retrieval:
            steps.append("retrieve_grounded_evidence" if source_available else "request_or_locate_grounded_evidence")
        if requires_tools:
            steps.append("execute_authorized_actions" if tool_available else "prepare_authorized_action_contract")
        if consider_alternatives:
            steps.append("compare_candidate_approaches")
        if requires_verification:
            steps.append("verify_result_against_goal_and_truth_boundary")
        steps.append("produce_final_response")

        stop_conditions = ["goal_satisfied", "truth_boundary_blocks_claim"]
        if requires_retrieval:
            stop_conditions.append("insufficient_grounded_evidence")
        if requires_tools:
            stop_conditions.append("tool_or_permission_unavailable")

        evidence.extend([
            f"complexity={complexity:.2f}",
            f"uncertainty={uncertainty:.2f}",
            f"mode={mode}",
        ])
        return ReasoningPlan(
            mode=mode,
            complexity_score=round(complexity, 4),
            uncertainty_score=round(uncertainty, 4),
            requires_retrieval=requires_retrieval,
            requires_tools=requires_tools,
            requires_verification=requires_verification,
            consider_alternatives=consider_alternatives,
            operational_steps=steps,
            stop_conditions=stop_conditions,
            evidence=evidence,
        )
