from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re
import unicodedata
from typing import Any, Iterable, Sequence

from latka_jazn.version import schema_version


SCHEMA_VERSION = schema_version("memory_slot_selector")
_SLOT_PLAN_SCHEMA = "memory_recall_slot_plan/v2"


@dataclass(frozen=True, slots=True)
class _Candidate:
    index: int
    item: Any
    evidence_id: str
    source_type: str
    item_type: str
    role: str
    kind: str
    text: str
    folded_text: str
    relevance: float
    confidence: float | None


class MemorySlotSelector:
    """Select evidence for recall slots by semantic role, not list position.

    Semantic slots are selected independently and, by default, cannot consume
    the same evidence record.  Metadata slots (time/source/truth/confidence)
    explicitly derive from the primary semantic evidence instead of pretending
    to be independent memories.  Missing semantic evidence becomes an
    `evidence_gap` record and is never filled from a generic first hit.
    """

    USER_ROLES = {"user", "human", "uzytkownik", "użytkownik"}
    LATKA_ROLES = {"assistant", "latka", "łatka", "ai"}
    REFLECTION_TYPES = {"journal_reflection"}
    MEMORY_TYPES = {"conversation_archive", "active_memory", "journal_reflection"}
    TECHNICAL_TYPES = {"technical_runtime", "source_code", "documentation", "runtime_status"}

    PREFERENCE_MARKERS = ("preferenc", "ulubion", "lubi", "wolę", "wole", "wybier", "podoba")
    PREFERENCE_REASON_MARKERS = ("ponieważ", "poniewaz", "dlatego", "bo ", "z powodu", "sprawia", "kojarzy")
    ORIGIN_MARKERS = ("powsta", "pochodz", "stworz", "począ", "pocza", "geneza", "źródło", "zrodlo")
    EVENT_MARKERS = ("byliśmy", "bylismy", "pojech", "wydarzy", "spotka", "pobyt", "wyjazd", "sytuac", "zdarzen")
    REFLECTION_MARKERS = ("refleks", "myśla", "mysla", "zastanaw", "wniosek", "później", "pozniej")

    def build_slot_plan(self, items: Sequence[Any], *, requested_slots: Sequence[str]) -> dict[str, Any]:
        requested = list(dict.fromkeys(str(slot) for slot in requested_slots if str(slot).strip()))
        candidates = self._candidates(items)
        slots: dict[str, dict[str, Any]] = {}
        used_semantic: set[str] = set()
        semantic_anchor_order: list[str] = []

        semantic_slots = [slot for slot in requested if slot not in self._metadata_slots()]
        for slot in semantic_slots:
            selection = self._select_semantic(slot, candidates, used_semantic)
            if selection is None:
                slots[slot] = self._gap(slot)
                continue
            candidate, value, extra = selection
            used_semantic.add(candidate.evidence_id)
            semantic_anchor_order.append(slot)
            slots[slot] = self._supported(slot, candidate, value=value, **extra)

        primary_anchor = self._primary_anchor(slots, semantic_anchor_order)
        for slot in requested:
            if slot in slots:
                continue
            if slot == "evidence_gap":
                missing_semantic = [name for name in semantic_slots if slots.get(name, {}).get("status") == "evidence_gap"]
                slots[slot] = {
                    "status": "supported" if missing_semantic else "evidence_gap",
                    "value": missing_semantic or None,
                    "source": None,
                    "semantic_source_type": None,
                    "truth_status": "unknown",
                    "confidence": None,
                    "provenance_label": "brak dowodu" if missing_semantic else "brak dowodu",
                    "timestamp": None,
                    "evidence_id": None,
                    "derived_from_slot": None,
                    "preference_status": None,
                    "origin_interpretation": None,
                    "biological_claim_allowed": None,
                }
                continue
            slots[slot] = self._metadata_from_anchor(slot, primary_anchor, slots)

        return {
            "schema_version": _SLOT_PLAN_SCHEMA,
            "selector_schema_version": SCHEMA_VERSION,
            "requested_slots": requested,
            "slots": slots,
            "evidence_gap_count": sum(1 for value in slots.values() if value.get("status") == "evidence_gap"),
            "semantic_evidence_ids": {
                slot: value.get("evidence_id")
                for slot, value in slots.items()
                if slot in semantic_slots and value.get("status") == "supported"
            },
            "truth_boundary": (
                "Każdy semantyczny slot jest dobierany według roli/typu źródła. "
                "Metadata jawnie dziedziczą po wskazanym evidence_id, a brak właściwego źródła pozostaje evidence_gap."
            ),
        }

    @staticmethod
    def _metadata_slots() -> set[str]:
        return {
            "time_context", "source", "truth_status", "confidence",
            "reflection_time", "reflection_provenance",
            "preference_provenance", "origin_time_or_boundary", "origin_provenance",
        }

    def _select_semantic(
        self,
        slot: str,
        candidates: list[_Candidate],
        used: set[str],
    ) -> tuple[_Candidate, Any, dict[str, Any]] | None:
        ranked: list[tuple[float, _Candidate]] = []
        for candidate in candidates:
            if candidate.evidence_id in used:
                continue
            score = self._score(slot, candidate)
            if score is not None:
                ranked.append((score, candidate))
        if not ranked:
            return None
        ranked.sort(key=lambda pair: (pair[0], pair[1].relevance, pair[1].confidence or 0.0), reverse=True)
        candidate = ranked[0][1]

        if slot == "origin_layer":
            value = self._origin_interpretation(candidate)
            return candidate, value, {"origin_interpretation": value, "biological_claim_allowed": False}
        if slot == "continuity_gap":
            return None
        if slot == "system_gap":
            value = candidate.text
            return candidate, value, {}
        if slot == "technical_evidence":
            return candidate, candidate.text, {}
        if slot == "architecture_status":
            return candidate, candidate.text, {}
        if slot == "architecture_sources":
            return candidate, candidate.item.source, {}
        if slot == "capability_status":
            return candidate, candidate.text, {}
        if slot.startswith("preference_"):
            return candidate, candidate.text, {"preference_status": self._preference_status(candidate)}
        return candidate, candidate.text, {}

    def _score(self, slot: str, candidate: _Candidate) -> float | None:
        source = candidate.source_type
        text = candidate.folded_text
        base = candidate.relevance + (candidate.confidence or 0.0) * 0.1

        if slot == "user_utterance":
            return base + 3.0 if candidate.role in self.USER_ROLES else None
        if slot == "latka_utterance":
            return base + 3.0 if candidate.role in self.LATKA_ROLES else None
        if slot in {"later_reflection", "reflection_content"}:
            reflection = source in self.REFLECTION_TYPES or "reflection" in candidate.kind or self._has(text, self.REFLECTION_MARKERS)
            return base + 2.8 if reflection else None
        if slot == "event_fact":
            if source not in {"conversation_archive", "active_memory"} and not candidate.item_type.startswith("episode"):
                return None
            if candidate.role in self.USER_ROLES | self.LATKA_ROLES and not self._has(text, self.EVENT_MARKERS):
                return None
            bonus = 2.5 if candidate.item_type.startswith("episode") or self._has(text, self.EVENT_MARKERS) else 1.5
            return base + bonus
        if slot == "preference_value":
            if source not in {"conversation_archive", "active_memory", "journal_reflection", "canon", "current_state", "inference"}:
                return None
            return base + 2.5 if self._has(text, self.PREFERENCE_MARKERS) else None
        if slot == "preference_reason":
            if source not in {"conversation_archive", "active_memory", "journal_reflection", "canon", "current_state", "inference"}:
                return None
            if not self._has(text, self.PREFERENCE_MARKERS) or not self._has(text, self.PREFERENCE_REASON_MARKERS):
                return None
            return base + 2.7
        if slot == "origin_layer":
            if source not in self.TECHNICAL_TYPES | {"canon", "conversation_archive", "active_memory", "journal_reflection", "inference"}:
                return None
            if source in self.TECHNICAL_TYPES or source == "canon" or self._has(text, self.ORIGIN_MARKERS):
                return base + self._origin_priority(source)
            return None
        if slot == "continuity_canon":
            return base + 3.0 if source == "canon" else None
        if slot == "continuity_memory":
            return base + 3.0 if source in self.MEMORY_TYPES else None
        if slot == "continuity_gap":
            return None
        if slot == "architecture_status":
            return base + 3.0 if source in self.TECHNICAL_TYPES else None
        if slot == "architecture_sources":
            return base + 3.0 if source in self.TECHNICAL_TYPES else None
        if slot == "capability_status":
            return base + 3.0 if source in {"runtime_status", "technical_runtime", "documentation"} else None
        if slot in {"system_gap", "technical_evidence"}:
            return base + 3.0 if source in {"source_code", "documentation", "runtime_status", "technical_runtime"} else None
        # Unknown semantic slots fail closed instead of receiving items[0].
        return None

    def _metadata_from_anchor(
        self,
        slot: str,
        primary_anchor: str | None,
        slots: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        preferred_anchor = primary_anchor
        if slot.startswith("reflection_") and slots.get("reflection_content", {}).get("status") == "supported":
            preferred_anchor = "reflection_content"
        elif slot.startswith("preference_") and slots.get("preference_value", {}).get("status") == "supported":
            preferred_anchor = "preference_value"
        elif slot.startswith("origin_") and slots.get("origin_layer", {}).get("status") == "supported":
            preferred_anchor = "origin_layer"

        anchor = slots.get(preferred_anchor or "") if preferred_anchor else None
        if not isinstance(anchor, dict) or anchor.get("status") != "supported":
            return self._gap(slot)

        if slot in {"time_context", "reflection_time", "origin_time_or_boundary"}:
            value = anchor.get("timestamp")
        elif slot in {"source", "reflection_provenance", "preference_provenance", "origin_provenance"}:
            value = anchor.get("provenance_label") if slot != "source" else anchor.get("source")
        elif slot == "truth_status":
            value = anchor.get("truth_status")
        elif slot == "confidence":
            value = anchor.get("confidence")
        else:
            value = None

        if value in {None, ""}:
            return self._gap(slot, derived_from_slot=preferred_anchor, evidence_id=anchor.get("evidence_id"))
        result = dict(anchor)
        result.update(
            {
                "status": "supported",
                "value": value,
                "derived_from_slot": preferred_anchor,
            }
        )
        return result

    @staticmethod
    def _primary_anchor(slots: dict[str, dict[str, Any]], order: Iterable[str]) -> str | None:
        priority = (
            "event_fact", "user_utterance", "latka_utterance", "later_reflection",
            "reflection_content", "preference_value", "origin_layer", "continuity_memory",
            "continuity_canon", "architecture_status", "capability_status",
        )
        for slot in priority:
            if slots.get(slot, {}).get("status") == "supported":
                return slot
        for slot in order:
            if slots.get(slot, {}).get("status") == "supported":
                return slot
        return None

    def _supported(
        self,
        slot: str,
        candidate: _Candidate,
        *,
        value: Any,
        preference_status: str | None = None,
        origin_interpretation: str | None = None,
        biological_claim_allowed: bool | None = None,
    ) -> dict[str, Any]:
        item = candidate.item
        return {
            "status": "supported" if value not in {None, ""} else "evidence_gap",
            "value": value,
            "source": getattr(item, "source", None),
            "semantic_source_type": candidate.source_type,
            "truth_status": getattr(item, "truth_status", None) or "unknown",
            "confidence": getattr(item, "confidence", None),
            "provenance_label": getattr(item, "provenance_label", None) or "brak dowodu",
            "timestamp": getattr(item, "timestamp", None),
            "evidence_id": candidate.evidence_id,
            "derived_from_slot": None,
            "preference_status": preference_status,
            "origin_interpretation": origin_interpretation,
            "biological_claim_allowed": biological_claim_allowed,
        }

    @staticmethod
    def _gap(
        slot: str,
        *,
        derived_from_slot: str | None = None,
        evidence_id: str | None = None,
    ) -> dict[str, Any]:
        return {
            "status": "evidence_gap",
            "value": None,
            "source": None,
            "semantic_source_type": None,
            "truth_status": "unknown",
            "confidence": None,
            "provenance_label": "brak dowodu",
            "timestamp": None,
            "evidence_id": evidence_id,
            "derived_from_slot": derived_from_slot,
            "preference_status": "unknown" if slot.startswith("preference_") else None,
            "origin_interpretation": "unknown" if slot.startswith("origin_") else None,
            "biological_claim_allowed": False if slot.startswith("origin_") else None,
        }

    def _candidates(self, items: Sequence[Any]) -> list[_Candidate]:
        values: list[_Candidate] = []
        for index, item in enumerate(items):
            text = str(getattr(item, "content_excerpt", "") or "").strip()
            if not text:
                continue
            metadata = getattr(item, "metadata", {})
            metadata = metadata if isinstance(metadata, dict) else {}
            source_type = str(getattr(item, "semantic_source_type", "") or "unknown")
            item_type = str(getattr(item, "item_type", "") or "unknown")
            role = self._fold(str(metadata.get("author_role") or ""))
            kind = self._fold(str(metadata.get("kind") or item_type))
            evidence_id = self._evidence_id(index, item)
            confidence = getattr(item, "confidence", None)
            try:
                relevance = float(getattr(item, "relevance_score", 0.0) or 0.0)
            except (TypeError, ValueError):
                relevance = 0.0
            values.append(
                _Candidate(
                    index=index,
                    item=item,
                    evidence_id=evidence_id,
                    source_type=source_type,
                    item_type=item_type,
                    role=role,
                    kind=kind,
                    text=text,
                    folded_text=self._fold(text),
                    relevance=relevance,
                    confidence=float(confidence) if isinstance(confidence, (int, float)) else None,
                )
            )
        return values

    @staticmethod
    def _evidence_id(index: int, item: Any) -> str:
        raw = "|".join(
            (
                str(index),
                str(getattr(item, "item_type", "") or ""),
                str(getattr(item, "source", "") or ""),
                str(getattr(item, "timestamp", "") or ""),
                str(getattr(item, "content_excerpt", "") or ""),
            )
        )
        return "mem:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]

    @staticmethod
    def _fold(text: str) -> str:
        normalized = unicodedata.normalize("NFKD", str(text or ""))
        folded = "".join(ch for ch in normalized if not unicodedata.combining(ch)).lower()
        return re.sub(r"\s+", " ", folded.replace("ł", "l")).strip()

    @classmethod
    def _has(cls, folded_text: str, markers: Sequence[str]) -> bool:
        return any(cls._fold(marker) in folded_text for marker in markers)

    @classmethod
    def _preference_status(cls, candidate: _Candidate) -> str:
        if candidate.source_type in {"conversation_archive", "active_memory", "journal_reflection"}:
            return "remembered_preference"
        if candidate.source_type == "canon":
            return "canonical_preference"
        if candidate.source_type == "current_state":
            return "current_preference"
        if candidate.source_type == "inference":
            return "inferred_preference"
        return "unknown"

    @classmethod
    def _origin_interpretation(cls, candidate: _Candidate) -> str:
        if candidate.source_type in cls.TECHNICAL_TYPES:
            return "technical_beginning"
        if candidate.source_type == "canon":
            return "canonical_origin"
        if candidate.source_type in cls.MEMORY_TYPES:
            return "relational_narrative_origin"
        if candidate.source_type == "inference":
            return "metaphorical_or_inferred_origin"
        return "unknown"

    @staticmethod
    def _origin_priority(source_type: str) -> float:
        return {
            "technical_runtime": 3.0,
            "source_code": 2.9,
            "documentation": 2.8,
            "runtime_status": 2.7,
            "canon": 2.6,
            "conversation_archive": 2.2,
            "active_memory": 2.1,
            "journal_reflection": 2.0,
            "inference": 1.0,
        }.get(source_type, 0.0)


__all__ = ["SCHEMA_VERSION", "MemorySlotSelector"]
