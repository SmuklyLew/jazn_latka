from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any, Iterable
import math
import re
import unicodedata

from latka_jazn.version import schema_version


SCHEMA_VERSION = schema_version("memory_source_policy")


class SemanticSourceType(StrEnum):
    """Semantic role of evidence, independent of its storage filename."""

    CONVERSATION_ARCHIVE = "conversation_archive"
    ACTIVE_EPISODIC_MEMORY = "active_episodic_memory"
    RUNTIME_WORKING_MEMORY = "runtime_working_memory"
    RUNTIME_SHORT_TERM_MEMORY = "runtime_short_term_memory"
    RUNTIME_LONG_TERM_MEMORY = "runtime_long_term_memory"
    JOURNAL_REFLECTION = "journal_reflection"
    CANON_IDENTITY = "canon_identity"
    CANON_PREFERENCE = "canon_preference"
    CURRENT_RUNTIME_STATE = "current_runtime_state"
    PROCEDURAL_MEMORY = "procedural_memory"
    TECHNICAL_SOURCE_CODE = "technical_source_code"
    TECHNICAL_DOCUMENTATION = "technical_documentation"
    DIAGNOSTIC_AUDIT = "diagnostic_audit"
    TEST_FIXTURE = "test_fixture"
    INFERENCE = "inference"
    UNKNOWN = "unknown"


AUTOBIOGRAPHICAL_SOURCE_ORDER: tuple[SemanticSourceType, ...] = (
    SemanticSourceType.CONVERSATION_ARCHIVE,
    SemanticSourceType.ACTIVE_EPISODIC_MEMORY,
    SemanticSourceType.RUNTIME_LONG_TERM_MEMORY,
    SemanticSourceType.RUNTIME_SHORT_TERM_MEMORY,
    SemanticSourceType.RUNTIME_WORKING_MEMORY,
    SemanticSourceType.JOURNAL_REFLECTION,
    SemanticSourceType.CANON_IDENTITY,
    SemanticSourceType.CANON_PREFERENCE,
    SemanticSourceType.INFERENCE,
)


@dataclass(frozen=True, slots=True)
class IntentSourcePolicy:
    intent: str
    question_object: str
    policy_kind: str
    priority_order: tuple[SemanticSourceType, ...]
    allowed_source_types: tuple[SemanticSourceType, ...]
    suppressed_source_types: tuple[SemanticSourceType, ...]
    evidence_gap_when_empty: bool = True
    technical_sources_allowed: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["priority_order"] = [item.value for item in self.priority_order]
        payload["allowed_source_types"] = [item.value for item in self.allowed_source_types]
        payload["suppressed_source_types"] = [item.value for item in self.suppressed_source_types]
        payload["schema_version"] = SCHEMA_VERSION
        return payload

    def priority_for(self, source_type: SemanticSourceType | str) -> float:
        semantic_type = coerce_source_type(source_type)
        if semantic_type in self.suppressed_source_types:
            return -math.inf
        if semantic_type not in self.allowed_source_types:
            return -math.inf
        try:
            index = self.priority_order.index(semantic_type)
        except ValueError:
            return 0.05
        return max(0.05, 1.0 - (index * 0.09))

    def allows(self, source_type: SemanticSourceType | str) -> bool:
        return math.isfinite(self.priority_for(source_type))


_AUTOBIOGRAPHICAL_INTENTS = {
    "memory_experience_question",
    "memory_recall_request",
    "self_memory_recall_request",
    "user_memory_recall_request",
    "memory_reflection_question",
    "memory_evidence_gap_question",
    "identity_memory_question",
    "continuity_question",
    "identity_continuity_question",
}
_PREFERENCE_INTENTS = {
    "self_preference_question",
    "preference_reason_question",
    "preference_provenance_question",
}
_TECHNICAL_INTENTS = {
    "memory_architecture_question",
    "capability_status_question",
    "memory_capability_question",
    "system_capability_gap_question",
    "system_diagnostic_question",
    "system_repair_plan_request",
    "logic_reasoning_audit_request",
    "self_architecture_audit_request",
}
_ORIGIN_INTENTS = {
    "origin_question",
    "origin_layer_question",
    "identity_direct_question",
}
_PROVENANCE_INTENTS = {
    "memory_provenance_question",
    "provenance_question",
    "epistemic_distinction_question",
}


def policy_for_intent(
    intent: str | None,
    *,
    question_object: str | None = None,
) -> IntentSourcePolicy:
    normalized_intent = str(intent or "unknown").strip() or "unknown"
    normalized_object = str(question_object or "unknown").strip() or "unknown"
    diagnostic = (
        SemanticSourceType.DIAGNOSTIC_AUDIT,
        SemanticSourceType.TEST_FIXTURE,
    )

    if normalized_intent in _TECHNICAL_INTENTS or normalized_object in {
        "memory_architecture",
        "system_module",
        "capability_gap",
        "runtime",
    }:
        order = (
            SemanticSourceType.TECHNICAL_SOURCE_CODE,
            SemanticSourceType.TECHNICAL_DOCUMENTATION,
            SemanticSourceType.PROCEDURAL_MEMORY,
            SemanticSourceType.CURRENT_RUNTIME_STATE,
            SemanticSourceType.DIAGNOSTIC_AUDIT,
            SemanticSourceType.CANON_IDENTITY,
            SemanticSourceType.INFERENCE,
        )
        return IntentSourcePolicy(
            normalized_intent,
            normalized_object,
            "technical",
            order,
            order,
            (SemanticSourceType.TEST_FIXTURE,),
            evidence_gap_when_empty=True,
            technical_sources_allowed=True,
        )

    if normalized_intent in _PREFERENCE_INTENTS or normalized_object in {
        "self_preference",
        "preference_reason",
        "preference_provenance",
    }:
        order = (
            SemanticSourceType.RUNTIME_LONG_TERM_MEMORY,
            SemanticSourceType.RUNTIME_SHORT_TERM_MEMORY,
            SemanticSourceType.ACTIVE_EPISODIC_MEMORY,
            SemanticSourceType.CONVERSATION_ARCHIVE,
            SemanticSourceType.JOURNAL_REFLECTION,
            SemanticSourceType.CANON_PREFERENCE,
            SemanticSourceType.CURRENT_RUNTIME_STATE,
            SemanticSourceType.INFERENCE,
        )
        return IntentSourcePolicy(
            normalized_intent,
            normalized_object,
            "preference",
            order,
            order,
            (
                *diagnostic,
                SemanticSourceType.PROCEDURAL_MEMORY,
                SemanticSourceType.TECHNICAL_SOURCE_CODE,
                SemanticSourceType.TECHNICAL_DOCUMENTATION,
            ),
        )

    if normalized_intent in _ORIGIN_INTENTS or normalized_object in {
        "origin",
        "birth_origin",
    }:
        order = (
            SemanticSourceType.CANON_IDENTITY,
            SemanticSourceType.CONVERSATION_ARCHIVE,
            SemanticSourceType.ACTIVE_EPISODIC_MEMORY,
            SemanticSourceType.RUNTIME_LONG_TERM_MEMORY,
            SemanticSourceType.CURRENT_RUNTIME_STATE,
            SemanticSourceType.TECHNICAL_DOCUMENTATION,
            SemanticSourceType.INFERENCE,
        )
        return IntentSourcePolicy(
            normalized_intent,
            normalized_object,
            "origin",
            order,
            order,
            (
                *diagnostic,
                SemanticSourceType.TEST_FIXTURE,
                SemanticSourceType.PROCEDURAL_MEMORY,
                SemanticSourceType.TECHNICAL_SOURCE_CODE,
            ),
            technical_sources_allowed=True,
        )

    if normalized_intent in _PROVENANCE_INTENTS or normalized_object in {
        "provenance",
        "epistemic_source",
    }:
        order = (
            *AUTOBIOGRAPHICAL_SOURCE_ORDER[:-1],
            SemanticSourceType.CURRENT_RUNTIME_STATE,
            SemanticSourceType.TECHNICAL_DOCUMENTATION,
            SemanticSourceType.INFERENCE,
        )
        return IntentSourcePolicy(
            normalized_intent,
            normalized_object,
            "provenance",
            order,
            order,
            diagnostic,
            technical_sources_allowed=True,
        )

    if normalized_intent in _AUTOBIOGRAPHICAL_INTENTS or normalized_object in {
        "memory_experience",
        "autobiographical_memory",
        "memory_evidence_gap",
        "shared_history",
    }:
        return IntentSourcePolicy(
            normalized_intent,
            normalized_object,
            "autobiographical",
            AUTOBIOGRAPHICAL_SOURCE_ORDER,
            AUTOBIOGRAPHICAL_SOURCE_ORDER,
            (
                *diagnostic,
                SemanticSourceType.PROCEDURAL_MEMORY,
                SemanticSourceType.TECHNICAL_SOURCE_CODE,
                SemanticSourceType.TECHNICAL_DOCUMENTATION,
            ),
        )

    order = (
        *AUTOBIOGRAPHICAL_SOURCE_ORDER,
        SemanticSourceType.CURRENT_RUNTIME_STATE,
        SemanticSourceType.TECHNICAL_DOCUMENTATION,
        SemanticSourceType.TECHNICAL_SOURCE_CODE,
        SemanticSourceType.PROCEDURAL_MEMORY,
    )
    return IntentSourcePolicy(
        normalized_intent,
        normalized_object,
        "general_fail_closed",
        order,
        order,
        diagnostic,
    )


def _fold(value: Any) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or "").casefold())
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    normalized = normalized.replace("ł", "l")
    return re.sub(r"\s+", " ", normalized).strip()


def coerce_source_type(value: SemanticSourceType | str | None) -> SemanticSourceType:
    if isinstance(value, SemanticSourceType):
        return value
    try:
        return SemanticSourceType(str(value or "unknown"))
    except ValueError:
        return SemanticSourceType.UNKNOWN


def classify_source_type(
    *,
    source_layer: Any = None,
    source_locator: Any = None,
    kind: Any = None,
    tier: Any = None,
    evidence_source_types: Iterable[Any] = (),
    metadata: dict[str, Any] | None = None,
) -> SemanticSourceType:
    metadata = metadata or {}
    parts = [
        source_layer,
        source_locator,
        kind,
        tier,
        metadata.get("source"),
        metadata.get("source_type"),
        metadata.get("grounding"),
        metadata.get("mode"),
        *evidence_source_types,
    ]
    joined = _fold(" ".join(str(part or "") for part in parts))

    if any(marker in joined for marker in (
        "chatgpt_runtime_preview",
        "chatgpt_dev_preview",
        "runtime_preview",
        "runtime-preview",
        "one_shot_preview",
        "diagnostic_preview",
    )):
        return SemanticSourceType.DIAGNOSTIC_AUDIT
    if any(marker in joined for marker in (
        "test_fixture",
        "synthetic_fixture",
        "pytest",
        "test-only",
        "test_only",
    )):
        return SemanticSourceType.TEST_FIXTURE
    if "procedural" in joined or "procedure" in joined:
        return SemanticSourceType.PROCEDURAL_MEMORY
    if str(tier or "") == "working" or "working_memory" in joined:
        return SemanticSourceType.RUNTIME_WORKING_MEMORY
    if str(tier or "") == "short_term" or "short_term_memory" in joined:
        return SemanticSourceType.RUNTIME_SHORT_TERM_MEMORY
    if str(tier or "") == "long_term" or "long_term_memory" in joined:
        return SemanticSourceType.RUNTIME_LONG_TERM_MEMORY
    if any(marker in joined for marker in ("archive_chats", "conversation_archive", "chat.html", "legacy_message")):
        return SemanticSourceType.CONVERSATION_ARCHIVE
    if any(marker in joined for marker in ("journal", "reflection", "dziennik")):
        return SemanticSourceType.JOURNAL_REFLECTION
    if any(marker in joined for marker in ("experience", "episodic", "memory_jazn")):
        return SemanticSourceType.ACTIVE_EPISODIC_MEMORY
    if "preference" in joined and "canon" in joined:
        return SemanticSourceType.CANON_PREFERENCE
    if "canon" in joined:
        return SemanticSourceType.CANON_IDENTITY
    if any(marker in joined for marker in ("runtime_state", "current_state", "operational_state")):
        return SemanticSourceType.CURRENT_RUNTIME_STATE
    if any(marker in joined for marker in (".py", "source_code", "source code", "module", "function", "class ")):
        return SemanticSourceType.TECHNICAL_SOURCE_CODE
    if any(marker in joined for marker in ("docs/", ".md", "documentation", "readme")):
        return SemanticSourceType.TECHNICAL_DOCUMENTATION
    if any(marker in joined for marker in ("inference", "inferred", "wniosk")):
        return SemanticSourceType.INFERENCE
    return SemanticSourceType.UNKNOWN


def epistemic_label(
    source_type: SemanticSourceType | str,
    *,
    truth_status: str | None = None,
) -> str:
    semantic_type = coerce_source_type(source_type)
    truth = _fold(truth_status)
    if truth in {"rejected", "quarantined", "invalid", "untrusted"}:
        return "brak_dowodu"
    if semantic_type is SemanticSourceType.CONVERSATION_ARCHIVE:
        return "odzyskano_z_archiwum"
    if semantic_type in {
        SemanticSourceType.ACTIVE_EPISODIC_MEMORY,
        SemanticSourceType.RUNTIME_WORKING_MEMORY,
        SemanticSourceType.RUNTIME_SHORT_TERM_MEMORY,
        SemanticSourceType.RUNTIME_LONG_TERM_MEMORY,
        SemanticSourceType.JOURNAL_REFLECTION,
    }:
        return "pamietam"
    if semantic_type in {
        SemanticSourceType.CANON_IDENTITY,
        SemanticSourceType.CANON_PREFERENCE,
    }:
        return "znam_z_kanonu"
    if semantic_type is SemanticSourceType.CURRENT_RUNTIME_STATE:
        return "biezacy_stan"
    if semantic_type is SemanticSourceType.INFERENCE:
        return "wnioskuje"
    return "brak_dowodu"
