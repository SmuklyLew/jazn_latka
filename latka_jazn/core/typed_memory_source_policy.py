from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

from latka_jazn.nlp.utterance_components import analyse_utterance
from latka_jazn.version import schema_version

SCHEMA_VERSION = schema_version("typed_memory_source_policy")

AUTOBIOGRAPHICAL_SOURCE_ORDER: tuple[str, ...] = (
    "conversation_archive",
    "active_memory",
    "journal_reflection",
    "canon",
    "current_state",
    "inference",
)
TECHNICAL_SOURCE_ORDER: tuple[str, ...] = (
    "source_code",
    "documentation",
    "procedural",
    "technical_runtime",
    "runtime_status",
    "canon",
    "active_memory",
    "conversation_archive",
    "inference",
)
DIAGNOSTIC_SOURCE_TYPE = "diagnostic_test"

_DIAGNOSTIC_MARKERS = (
    "chatgpt_runtime_preview",
    "chatgpt_dev_preview",
    "runtime_preview",
    "diagnostic_preview",
    "test_fixture",
    "test-fixture",
    "synthetic_fixture",
    "synthetic-fixture",
)
_CANON_MARKERS = (
    "canon",
    "identity_canon",
    "latka_identity_canon",
    "origin_story",
    "character_profile",
    "relation_canon",
    "narrative_book_canon",
)
_JOURNAL_MARKERS = (
    "journal",
    "dziennik",
    "reflection",
    "reflections",
    "grounded_reflection",
)
_ARCHIVE_MARKERS = (
    "archive_chats",
    "conversation_archive",
    "legacy_message",
    "legacy_import",
    "chat.html",
    "chat_html",
    "raw_chat",
    "conversation_turn",
)
_ACTIVE_MEMORY_MARKERS = (
    "memory_jazn",
    "runtime_write_v2",
    "transactional_tier",
    "working_memory",
    "short_term",
    "long_term",
    "episodic",
    "episode",
    "experience",
    "living_memory",
)
_CODE_MARKERS = (
    ".py",
    "source_code",
    "source-file",
    "source_file",
    "implementation",
    "module",
)
_DOC_MARKERS = (
    ".md",
    ".rst",
    "documentation",
    "docs/",
    "readme",
)
_PROCEDURAL_MARKERS = (
    "procedural",
    "procedure",
    "runbook",
    "instructions",
    "workflow",
    "patch",
)
_RUNTIME_MARKERS = (
    "runtime_status",
    "technical_runtime",
    "daemon",
    "doctor",
    "heartbeat",
    "workspace_runtime",
)
_CURRENT_STATE_MARKERS = (
    "current_state",
    "self_state",
    "operational_state",
)
_INFERENCE_MARKERS = (
    "inference",
    "inferred",
    "wniosek",
    "reasoning",
)


@dataclass(frozen=True, slots=True)
class TypedSourceDecision:
    semantic_source_type: str
    allowed: bool
    priority: int
    suppression_reason: str | None
    provenance_label: str
    truth_boundary: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class TypedMemorySourcePolicy:
    intent_family: str
    requested_semantic_intents: tuple[str, ...]
    priority_order: tuple[str, ...]
    allowed_source_types: tuple[str, ...]
    suppressed_source_types: tuple[str, ...]
    evidence_gap_on_empty: bool = True
    schema_version: str = SCHEMA_VERSION
    truth_boundary: str = (
        "Typ źródła i zgodność z intencją wpływają na ranking, ale nie tworzą faktów. "
        "Materiały diagnostyczne/testowe są tłumione w recallu autobiograficznym; brak "
        "właściwego źródła kończy się evidence gap zamiast zastąpieniem go przypadkowym trafieniem."
    )

    def priority_for(self, semantic_source_type: str) -> int:
        try:
            index = self.priority_order.index(semantic_source_type)
        except ValueError:
            return 0
        return max(1, 100 - index * 10)

    def allows(self, semantic_source_type: str) -> bool:
        return semantic_source_type in self.allowed_source_types

    def evaluate(
        self,
        *,
        item_type: str | None = None,
        source: str | None = None,
        source_layer: str | None = None,
        grounding: str | None = None,
        path: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> TypedSourceDecision:
        semantic_type = classify_semantic_source_type(
            item_type=item_type,
            source=source,
            source_layer=source_layer,
            grounding=grounding,
            path=path,
            metadata=metadata,
        )
        allowed = self.allows(semantic_type)
        suppression_reason: str | None = None
        if semantic_type == DIAGNOSTIC_SOURCE_TYPE:
            allowed = False
            suppression_reason = "diagnostic_or_preview_source_suppressed"
        elif not allowed:
            suppression_reason = f"source_type_not_allowed_for_{self.intent_family}"
        return TypedSourceDecision(
            semantic_source_type=semantic_type,
            allowed=allowed,
            priority=self.priority_for(semantic_type) if allowed else 0,
            suppression_reason=suppression_reason,
            provenance_label=provenance_label_for_source_type(semantic_type),
            truth_boundary=self.truth_boundary,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _blob(*values: Any) -> str:
    parts: list[str] = []
    for value in values:
        if value is None:
            continue
        if isinstance(value, dict):
            for key, nested in value.items():
                parts.append(str(key))
                parts.append(str(nested))
        elif isinstance(value, (list, tuple, set)):
            parts.extend(str(part) for part in value)
        else:
            parts.append(str(value))
    return " ".join(parts).lower().replace("\\", "/")


def _has(blob: str, markers: Iterable[str]) -> bool:
    return any(marker in blob for marker in markers)


def classify_semantic_source_type(
    *,
    item_type: str | None = None,
    source: str | None = None,
    source_layer: str | None = None,
    grounding: str | None = None,
    path: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> str:
    blob = _blob(item_type, source, source_layer, grounding, path, metadata)
    # Explicit diagnostic provenance always wins; it must never become an
    # autobiographical memory just because it contains a personal keyword.
    if _has(blob, _DIAGNOSTIC_MARKERS):
        return DIAGNOSTIC_SOURCE_TYPE
    if _has(blob, _JOURNAL_MARKERS):
        return "journal_reflection"
    if _has(blob, _ARCHIVE_MARKERS):
        return "conversation_archive"
    if _has(blob, _CANON_MARKERS):
        return "canon"
    if _has(blob, _CURRENT_STATE_MARKERS):
        return "current_state"
    if _has(blob, _INFERENCE_MARKERS):
        return "inference"
    if _has(blob, _RUNTIME_MARKERS):
        return "technical_runtime"
    if _has(blob, _PROCEDURAL_MARKERS):
        return "procedural"
    if _has(blob, _DOC_MARKERS):
        return "documentation"
    if _has(blob, _CODE_MARKERS):
        return "source_code"
    if _has(blob, _ACTIVE_MEMORY_MARKERS):
        return "active_memory"
    # A source file extension is stronger evidence than an untyped generic label.
    if path:
        suffix = Path(str(path)).suffix.lower()
        if suffix == ".py":
            return "source_code"
        if suffix in {".md", ".rst"}:
            return "documentation"
    return "unknown"


def provenance_label_for_source_type(semantic_source_type: str) -> str:
    if semantic_source_type == "conversation_archive":
        return "odzyskano z archiwum"
    if semantic_source_type in {"active_memory", "journal_reflection"}:
        return "pamiętam"
    if semantic_source_type == "canon":
        return "znam z kanonu"
    if semantic_source_type == "current_state":
        return "bieżący stan"
    if semantic_source_type == "inference":
        return "wnioskuję"
    if semantic_source_type == DIAGNOSTIC_SOURCE_TYPE:
        return "materiał diagnostyczny — wyłączony z recallu"
    if semantic_source_type in {
        "technical_runtime",
        "runtime_status",
        "source_code",
        "documentation",
        "procedural",
    }:
        return "źródło techniczne"
    return "brak dowodu"


def build_typed_source_policy(user_text: str) -> TypedMemorySourcePolicy:
    report = analyse_utterance(user_text)
    semantic_intents = tuple(dict.fromkeys(report.semantic_intents))
    autobiographical = any(
        intent in {
            "memory_recall",
            "self_preference",
            "self_origin",
            "self_introspection",
            "identity_continuity",
            "provenance",
            "evidence_gap",
        }
        for intent in semantic_intents
    )
    technical = any(
        intent in {"memory_architecture", "system_capability_gap"}
        for intent in semantic_intents
    )
    capability_only = bool(report.capability_only and not autobiographical)

    if autobiographical and technical:
        family = "mixed"
        order = tuple(dict.fromkeys((*AUTOBIOGRAPHICAL_SOURCE_ORDER, *TECHNICAL_SOURCE_ORDER)))
        allowed = order
    elif technical or capability_only:
        family = "technical"
        order = TECHNICAL_SOURCE_ORDER
        allowed = order
    elif autobiographical:
        family = "autobiographical"
        order = AUTOBIOGRAPHICAL_SOURCE_ORDER
        allowed = order
    else:
        family = "general"
        order = tuple(dict.fromkeys((*AUTOBIOGRAPHICAL_SOURCE_ORDER, *TECHNICAL_SOURCE_ORDER)))
        allowed = order

    return TypedMemorySourcePolicy(
        intent_family=family,
        requested_semantic_intents=semantic_intents,
        priority_order=order,
        allowed_source_types=allowed,
        suppressed_source_types=(DIAGNOSTIC_SOURCE_TYPE,),
    )


__all__ = [
    "AUTOBIOGRAPHICAL_SOURCE_ORDER",
    "DIAGNOSTIC_SOURCE_TYPE",
    "SCHEMA_VERSION",
    "TECHNICAL_SOURCE_ORDER",
    "TypedMemorySourcePolicy",
    "TypedSourceDecision",
    "build_typed_source_policy",
    "classify_semantic_source_type",
    "provenance_label_for_source_type",
]
