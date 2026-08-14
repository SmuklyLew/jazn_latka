from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import json
import uuid
from typing import Any, Iterable

SCHEMA_VERSION = "cognitive_lineage/v1"
OBSERVATION_SCHEMA_VERSION = "cognitive_lineage_observation/v1"

# Stable namespace used only to derive opaque, turn-scoped correlation IDs.
# The derived IDs contain no user text, memory excerpt, source path or claim body.
_LINEAGE_NAMESPACE = uuid.UUID("7fbdb9dd-0937-4e8f-bd83-0e41cc102e73")
_VALID_CATEGORIES = frozenset({"goal", "constraint", "evidence"})


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _clean_token(value: Any, *, fallback: str = "unknown") -> str:
    text = str(value or "").strip()
    if not text:
        return fallback
    return "".join(ch if ch.isalnum() or ch in "._:/-" else "_" for ch in text).strip("_") or fallback


def _normalize_refs(values: Iterable[Any] | None) -> tuple[str, ...]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in values or ():
        value = str(raw or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        out.append(value)
    return tuple(out)


def _normalize_categories(values: Iterable[str] | None) -> tuple[str, ...]:
    out: list[str] = []
    for raw in values or ():
        value = str(raw or "").strip().lower()
        if value in _VALID_CATEGORIES and value not in out:
            out.append(value)
    return tuple(out)


def _thought_id_for_turn(turn_id: str) -> str:
    return str(uuid.uuid5(_LINEAGE_NAMESPACE, f"turn:{turn_id}"))


def _opaque_semantic_id(thought_id: str, category: str, reference: str) -> str:
    namespace = uuid.UUID(thought_id)
    return str(uuid.uuid5(namespace, f"{category}:{reference}"))


def resolve_parent_thought_id(client_context: dict[str, Any] | None) -> str | None:
    """Read an explicitly supplied parent correlation without inventing carry-over.

    PR v15.5 lineage runs in shadow mode. It therefore does not infer cross-turn
    parentage from topic similarity, old task state or conversation history. A
    parent link is accepted only when the caller provides one explicitly.
    """

    context = dict(client_context or {})
    candidates = [
        context.get("parent_thought_id"),
        context.get("previous_thought_id"),
    ]
    previous_lineage = context.get("previous_cognitive_lineage")
    if isinstance(previous_lineage, dict):
        candidates.append(previous_lineage.get("thought_id"))
    for raw in candidates:
        value = str(raw or "").strip()
        if not value:
            continue
        try:
            return str(uuid.UUID(value))
        except (ValueError, TypeError, AttributeError):
            continue
    return None


def constraint_references_from_policy(policy: dict[str, Any] | None) -> tuple[str, ...]:
    """Return non-secret operational constraint references from a response policy.

    Only control-plane keys are represented. Values are not copied into lineage;
    they are used solely as input for opaque UUID5 identifiers.
    """

    source = dict(policy or {})
    keys = (
        "exact_runtime_required",
        "allow_memory_content",
        "allow_online_lookup",
        "source_grounding_required",
        "requires_diagnostic",
        "llm_allowed",
        "memory_gate",
        "answer_kind",
    )
    refs: list[str] = []
    for key in keys:
        if key not in source or source.get(key) is None:
            continue
        value = source.get(key)
        if isinstance(value, (str, int, float, bool)):
            refs.append(f"{key}={value}")
    return _normalize_refs(refs)


def evidence_references_from_memory_contract(
    memory_recall_contract: dict[str, Any] | None,
) -> tuple[str, ...]:
    """Build stable evidence references without retaining recalled content.

    The function intentionally ignores ``content``/``excerpt`` fields. When a
    durable memory/source identifier exists in metadata it is preferred;
    otherwise a bounded structural locator is derived from source/type/time and
    item position. The returned references are immediately converted to opaque
    turn-scoped identifiers by :class:`CognitiveLineage`.
    """

    contract = dict(memory_recall_contract or {})
    refs: list[str] = []
    identity_keys = (
        "memory_id",
        "item_id",
        "id",
        "source_id",
        "source_locator",
        "conversation_id",
        "message_id",
        "node_id",
        "segment_id",
        "snapshot_id",
    )
    for index, raw in enumerate(contract.get("items") or []):
        if not isinstance(raw, dict):
            continue
        item: dict[str, Any] = dict(raw)
        metadata_value = item.get("metadata")
        metadata: dict[str, Any] = (
            dict(metadata_value) if isinstance(metadata_value, dict) else {}
        )
        durable_parts: list[str] = []
        for key in identity_keys:
            value = item.get(key)
            if value in (None, ""):
                value = metadata.get(key)
            if value not in (None, ""):
                durable_parts.append(f"{key}:{value}")
        if durable_parts:
            refs.append("|".join(durable_parts))
            continue
        source = str(item.get("source") or item.get("memory_type") or "runtime_memory")
        memory_type = str(item.get("memory_type") or "unknown")
        timestamp = str(item.get("timestamp") or "")
        refs.append(f"fallback:{index}:{source}:{memory_type}:{timestamp}")
    return _normalize_refs(refs)


def evidence_references_from_selected_sources(
    sources: Iterable[dict[str, Any]] | None,
) -> tuple[str, ...]:
    refs: list[str] = []
    for index, raw in enumerate(sources or ()):
        if not isinstance(raw, dict):
            continue
        item_id = str(raw.get("item_id") or "").strip()
        if item_id:
            refs.append(f"item_id:{item_id}")
            continue
        source = str(raw.get("source") or "runtime_memory")
        timestamp = str(raw.get("timestamp") or "")
        refs.append(f"fallback:{index}:{source}:{timestamp}")
    return _normalize_refs(refs)


@dataclass(slots=True, frozen=True)
class CognitiveLineageObservation:
    sequence: int
    stage: str
    event: str
    source: str
    goal_ids: tuple[str, ...] = ()
    constraint_ids: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    route_id: str | None = None
    candidate_id: str | None = None
    expected_categories: tuple[str, ...] = ()
    missing_required_ids: dict[str, tuple[str, ...]] = field(default_factory=dict)
    continuity_ok: bool = True
    state_sha256: str = ""
    schema_version: str = OBSERVATION_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["goal_ids"] = list(self.goal_ids)
        data["constraint_ids"] = list(self.constraint_ids)
        data["evidence_ids"] = list(self.evidence_ids)
        data["expected_categories"] = list(self.expected_categories)
        data["missing_required_ids"] = {
            key: list(value) for key, value in self.missing_required_ids.items()
        }
        return data


@dataclass(slots=True)
class CognitiveLineage:
    """Shadow-only semantic correlation for one runtime turn.

    This structure is deliberately *not* a private reasoning trace. It records
    only opaque identifiers for explicit runtime artefacts (goal, constraints,
    evidence, route and selected candidate) and whether expected identifiers are
    observable at named module hand-offs.
    """

    thought_id: str
    turn_id: str
    trace_id: str
    parent_thought_id: str | None = None
    anchored_goal_ids: list[str] = field(default_factory=list)
    anchored_constraint_ids: list[str] = field(default_factory=list)
    anchored_evidence_ids: list[str] = field(default_factory=list)
    observations: list[CognitiveLineageObservation] = field(default_factory=list)
    lineage_break_count: int = 0
    shadow_mode: bool = True
    schema_version: str = SCHEMA_VERSION
    truth_boundary: str = (
        "Cognitive lineage is an operational correlation trace, not private chain-of-thought, "
        "biological cognition, memory truth or proof that a semantic concept was understood. "
        "It records only opaque IDs and explicit hand-off observations; shadow mode cannot alter routing or generation."
    )

    @classmethod
    def create(
        cls,
        *,
        turn_id: str,
        trace_id: str,
        parent_thought_id: str | None = None,
    ) -> "CognitiveLineage":
        normalized_turn = str(turn_id or "").strip()
        normalized_trace = str(trace_id or "").strip()
        if not normalized_turn:
            raise ValueError("turn_id is required for cognitive lineage")
        if not normalized_trace:
            raise ValueError("trace_id is required for cognitive lineage")
        parent = None
        if parent_thought_id:
            try:
                parent = str(uuid.UUID(str(parent_thought_id)))
            except (ValueError, TypeError, AttributeError) as exc:
                raise ValueError("parent_thought_id must be a UUID") from exc
        lineage = cls(
            thought_id=_thought_id_for_turn(normalized_turn),
            turn_id=normalized_turn,
            trace_id=normalized_trace,
            parent_thought_id=parent,
        )
        lineage.observe(stage="envelope_created", event="lineage_initialized", source="cognitive_turn_envelope")
        return lineage

    def _id_set(self, category: str, references: Iterable[Any] | None) -> tuple[str, ...]:
        if category not in _VALID_CATEGORIES:
            raise ValueError(f"unsupported lineage category: {category}")
        return tuple(
            sorted(
                {
                    _opaque_semantic_id(self.thought_id, category, reference)
                    for reference in _normalize_refs(references)
                }
            )
        )

    def _route_id(self, route_ref: Any | None) -> str | None:
        route = str(route_ref or "").strip()
        if not route:
            return None
        return _opaque_semantic_id(self.thought_id, "route", route)

    def _candidate_id(self, candidate_ref: Any | None) -> str | None:
        candidate = str(candidate_ref or "").strip()
        if not candidate:
            return None
        return _opaque_semantic_id(self.thought_id, "candidate", candidate)

    def _anchor(self, category: str, identifiers: tuple[str, ...]) -> None:
        target = {
            "goal": self.anchored_goal_ids,
            "constraint": self.anchored_constraint_ids,
            "evidence": self.anchored_evidence_ids,
        }[category]
        for identifier in identifiers:
            if identifier not in target:
                target.append(identifier)
        target.sort()

    def _required_for(self, category: str) -> tuple[str, ...]:
        return tuple(
            {
                "goal": self.anchored_goal_ids,
                "constraint": self.anchored_constraint_ids,
                "evidence": self.anchored_evidence_ids,
            }[category]
        )

    def observe(
        self,
        *,
        stage: str,
        event: str,
        source: str,
        goal_refs: Iterable[Any] | None = None,
        constraint_refs: Iterable[Any] | None = None,
        evidence_refs: Iterable[Any] | None = None,
        route_ref: Any | None = None,
        candidate_ref: Any | None = None,
        anchor_categories: Iterable[str] | None = None,
        expect_categories: Iterable[str] | None = None,
    ) -> CognitiveLineageObservation:
        stage_token = _clean_token(stage, fallback="unknown_stage")
        event_token = _clean_token(event, fallback="observation")
        source_token = _clean_token(source, fallback="runtime")
        goals = self._id_set("goal", goal_refs)
        constraints = self._id_set("constraint", constraint_refs)
        evidence = self._id_set("evidence", evidence_refs)
        observed = {
            "goal": goals,
            "constraint": constraints,
            "evidence": evidence,
        }
        for category in _normalize_categories(anchor_categories):
            self._anchor(category, observed[category])

        expected = _normalize_categories(expect_categories)
        missing: dict[str, tuple[str, ...]] = {}
        for category in expected:
            required = set(self._required_for(category))
            absent = tuple(sorted(required.difference(observed[category])))
            if absent:
                missing[category] = absent

        route_id = self._route_id(route_ref)
        candidate_id = self._candidate_id(candidate_ref)
        state_payload = {
            "thought_id": self.thought_id,
            "turn_id": self.turn_id,
            "trace_id": self.trace_id,
            "parent_thought_id": self.parent_thought_id,
            "stage": stage_token,
            "event": event_token,
            "source": source_token,
            "goal_ids": goals,
            "constraint_ids": constraints,
            "evidence_ids": evidence,
            "route_id": route_id,
            "candidate_id": candidate_id,
            "anchored_goal_ids": tuple(self.anchored_goal_ids),
            "anchored_constraint_ids": tuple(self.anchored_constraint_ids),
            "anchored_evidence_ids": tuple(self.anchored_evidence_ids),
            "expected_categories": expected,
            "missing_required_ids": missing,
            "shadow_mode": self.shadow_mode,
        }
        observation = CognitiveLineageObservation(
            sequence=len(self.observations) + 1,
            stage=stage_token,
            event=event_token,
            source=source_token,
            goal_ids=goals,
            constraint_ids=constraints,
            evidence_ids=evidence,
            route_id=route_id,
            candidate_id=candidate_id,
            expected_categories=expected,
            missing_required_ids=missing,
            continuity_ok=not missing,
            state_sha256=_sha256_json(state_payload),
        )
        self.observations.append(observation)
        if missing:
            self.lineage_break_count += 1
        return observation

    @property
    def latest_state_sha256(self) -> str | None:
        return self.observations[-1].state_sha256 if self.observations else None

    @property
    def latest_observation(self) -> CognitiveLineageObservation | None:
        return self.observations[-1] if self.observations else None

    def summary(self) -> dict[str, Any]:
        return {
            "thought_id": self.thought_id,
            "parent_thought_id": self.parent_thought_id,
            "anchored_goal_ids": list(self.anchored_goal_ids),
            "anchored_constraint_ids": list(self.anchored_constraint_ids),
            "anchored_evidence_ids": list(self.anchored_evidence_ids),
            "lineage_observation_count": len(self.observations),
            "lineage_break_count": self.lineage_break_count,
            "lineage_state_sha256": self.latest_state_sha256,
            "lineage_shadow_mode": self.shadow_mode,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "thought_id": self.thought_id,
            "turn_id": self.turn_id,
            "trace_id": self.trace_id,
            "parent_thought_id": self.parent_thought_id,
            "anchored_goal_ids": list(self.anchored_goal_ids),
            "anchored_constraint_ids": list(self.anchored_constraint_ids),
            "anchored_evidence_ids": list(self.anchored_evidence_ids),
            "observations": [item.to_dict() for item in self.observations],
            "observation_count": len(self.observations),
            "lineage_break_count": self.lineage_break_count,
            "latest_state_sha256": self.latest_state_sha256,
            "shadow_mode": self.shadow_mode,
            "truth_boundary": self.truth_boundary,
        }
