from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, asdict, field
from datetime import datetime
import math
from typing import Any
import re

from latka_jazn.core.typed_memory_source_policy import (
    build_typed_source_policy,
    provenance_label_for_source_type,
)
from latka_jazn.nlp.utterance_components import analyse_utterance
from latka_jazn.core.memory_slot_selector import MemorySlotSelector

@dataclass(slots=True)
class MemoryRecallItem:
    """Treściowy trop pamięci przekazywany do warstwy odpowiedzi.

    poprzednia linia runtime naprawia błąd, w którym runtime znał listę epizodów
    i legacy_messages, ale widoczna odpowiedź dostawała głównie liczniki.
    Ten obiekt jest mały, jawny i bezpieczny do włączenia w cognitive-frame
    albo ConversationDecision: zawiera treść, źródło, czas, typ, pewność
    i prostą ocenę trafności/znaczenia. poprzednia linia runtime dodaje też tropy z plików kanonicznych planera pamięci.
    """

    item_type: str
    query_term: str | None
    timestamp: str | None
    source: str | None
    confidence: float | None
    grounding: str | None
    relevance_score: float
    relevance_label: str
    meaning_assessment: str
    content_excerpt: str
    semantic_source_type: str = "unknown"
    truth_status: str = "unknown"
    provenance_label: str = "brak dowodu"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class MemoryRecallPresenter:
    """Buduje i renderuje treściowe przypomnienie zamiast samych `counts`.

    Zasada projektowa: licznik jest diagnostyką, nie pamięcią. Odpowiedź
    rozmowna ma dostać realne fragmenty wspomnień oraz ocenę, czy są
    znaczeniowo trafne, czy jedynie przypadkowo/leksykalnie znalezione.
    """

    TECHNICAL_MARKERS = (
        "def ", "class ", "import ", "sqlite", "traceback", "pytest", "manifest",
        "update_report", "patch", "runtime", "fallback", "zip", "github", "jsonl",
        "main.py", "engine.py", "conversation.py", "legacy_messages", "episodes=",
    )
    TECHNICAL_QUERY_MARKERS = (
        "system", "runtime", "plik", "kod", "patch", "aktualizac", "wersj", "zip",
        "test", "debug", "fallback", "github", "sqlite", "manifest", "jaźni", "jazni",
    )

    def build_items(self, memory_context: dict[str, Any] | None, *, user_text: str = "", limit: int = 6) -> list[MemoryRecallItem]:
        if not isinstance(memory_context, dict):
            return []
        terms = [str(x) for x in (memory_context.get("query_terms") or []) if str(x).strip()]
        items: list[MemoryRecallItem] = []
        temporal_scope = self._temporal_scope_from_context(memory_context)

        living_hits = self.filter_temporal_candidates(
            memory_context.get("living_memory_hits") or [],
            temporal_scope=temporal_scope,
            timestamp_fields=("timestamp",),
        )
        for hit in living_hits:
            if not isinstance(hit, dict):
                continue
            content = self._clean(hit.get("content_excerpt") or hit.get("content"))
            if not content:
                continue
            if not self._source_item_allowed(hit, content=content, user_text=user_text):
                continue
            confidence = self._float_or_none(hit.get("confidence"))
            base_score, label, assessment = self._assess(content, terms, user_text, confidence=confidence)
            gateway_score = self._float_or_none(hit.get("relevance"))
            score = max(base_score, gateway_score or 0.0)
            if score >= 0.62:
                label = "wysoka"
            elif score >= 0.43:
                label = "średnia"
            else:
                label = "słaba"
            layer = self._clean(hit.get("source_layer")) or "living_memory"
            truth_status = self._clean(hit.get("truth_status")) or "source_recorded"
            assessment = (
                f"odczyt tylko do odczytu z warstwy {layer}; truth_status={truth_status}; "
                "trafienie jest źródłem lub zapisem, nie automatycznym wspomnieniem L3"
            )
            source_parts = [self._clean(hit.get("source_database")), self._clean(hit.get("source_locator"))]
            source = " / ".join(part for part in source_parts if part) or layer
            items.append(MemoryRecallItem(
                item_type=f"living_memory:{layer}",
                query_term=self._first_matching_term(content, terms),
                timestamp=self._clean(hit.get("timestamp")),
                source=source,
                confidence=confidence,
                grounding=self._clean(hit.get("grounding")) or "read_only_living_memory_gateway",
                relevance_score=score,
                relevance_label=label,
                meaning_assessment=assessment,
                content_excerpt=self._excerpt(content, max_len=520),
                truth_status=truth_status,
                metadata={
                    **(hit.get("metadata") if isinstance(hit.get("metadata"), dict) else {}),
                    "source_layer": layer,
                    "source_database": self._clean(hit.get("source_database")),
                },
            ))

        episodes = self.filter_temporal_candidates(
            memory_context.get("episodes") or [],
            temporal_scope=temporal_scope,
            timestamp_fields=("created_at_utc", "local_time_label", "timestamp"),
        )
        for ep in episodes:
            if not isinstance(ep, dict):
                continue
            content = self._clean(ep.get("scene"))
            if not content:
                continue
            if not self._source_item_allowed(ep, content=content, user_text=user_text):
                continue
            confidence = self._float_or_none(ep.get("confidence"))
            score, label, assessment = self._assess(content, terms, user_text, confidence=confidence)
            items.append(MemoryRecallItem(
                item_type="episode",
                query_term=self._first_matching_term(content, terms) or ep.get("phrase"),
                timestamp=self._clean(ep.get("local_time_label")),
                source=self._clean(ep.get("source")) or "memory/layered",
                confidence=confidence,
                grounding=self._clean(ep.get("grounding")),
                relevance_score=score,
                relevance_label=label,
                meaning_assessment=assessment,
                content_excerpt=self._excerpt(content),
                truth_status=self._clean(ep.get("truth_status") or ep.get("review_status")) or "source_recorded",
                metadata={
                    "author_role": self._clean(ep.get("author_role")),
                    "kind": self._clean(ep.get("kind")),
                },
            ))

        legacy_messages = self.filter_temporal_candidates(
            memory_context.get("legacy_messages") or [],
            temporal_scope=temporal_scope,
            timestamp_fields=(
                "create_time",
                "create_time_warsaw",
                "created_at_utc",
                "created_at_local",
            ),
        )
        for row in legacy_messages:
            if not isinstance(row, dict):
                continue
            content = self._clean(row.get("text"))
            if not content:
                continue
            if not self._source_item_allowed(row, content=content, user_text=user_text):
                continue
            score, label, assessment = self._assess(content, terms, user_text, confidence=None)
            title = self._clean(row.get("conversation_title"))
            role = self._clean(row.get("author_role"))
            source = "chat.html"
            if title or role:
                source = f"chat.html / {title or 'bez tytułu'} / {role or 'unknown'}"
            items.append(MemoryRecallItem(
                item_type="legacy_message",
                query_term=self._first_matching_term(content, terms) or row.get("phrase"),
                timestamp=self._clean(row.get("create_time_warsaw")),
                source=source,
                confidence=None,
                grounding="legacy_import_index",
                relevance_score=score,
                relevance_label=label,
                meaning_assessment=assessment,
                content_excerpt=self._excerpt(content),
                truth_status=self._clean(row.get("truth_status") or row.get("review_status")) or "source_recorded",
                metadata={"author_role": role, "conversation_title": title},
            ))


        source_file_hits = self.filter_temporal_candidates(
            memory_context.get("source_file_hits") or [],
            temporal_scope=temporal_scope,
            timestamp_fields=("event_timestamp", "timestamp", "created_at_utc"),
        )
        for hit in source_file_hits:
            if not isinstance(hit, dict):
                continue
            content = self._clean(hit.get("content_excerpt"))
            if not content:
                continue
            if not self._source_item_allowed(hit, content=content, user_text=user_text):
                continue
            base_score, label, assessment = self._assess(content, terms, user_text, confidence=None)
            planner_score = self._float_or_none(hit.get("score"))
            score = max(base_score, planner_score or 0.0)
            if score >= 0.62:
                label = "wysoka"
            elif score >= 0.43:
                label = "średnia"
            else:
                label = "słaba"
            if hit.get("source_label") == "canonical_source_file":
                assessment = "kanoniczny plik źródłowy wskazany przez planer pamięci; dobry trop do odpowiedzi, ale nadal trzeba zachować granicę prawdy"
            items.append(MemoryRecallItem(
                item_type="source_file",
                query_term=self._clean(hit.get("term")) or self._first_matching_term(content, terms),
                timestamp=self._clean(
                    hit.get("event_timestamp")
                    or hit.get("timestamp")
                    or hit.get("created_at_utc")
                ),
                source=self._clean(hit.get("path")) or "canonical_source_file",
                confidence=None,
                grounding=self._clean(hit.get("source_label")) or "memory_search_planner",
                relevance_score=score,
                relevance_label=label,
                meaning_assessment=assessment,
                content_excerpt=self._excerpt(content, max_len=420),
                truth_status=self._clean(hit.get("truth_status")) or "source_recorded",
                semantic_source_type=self._clean(hit.get("semantic_source_type")) or "unknown",
                provenance_label=self._clean(hit.get("provenance_label")) or "brak dowodu",
                metadata={"topic_key": hit.get("topic_key"), "path": self._clean(hit.get("path"))},
            ))

        archive_hits = self.filter_temporal_candidates(
            memory_context.get("conversation_archive_hits") or [],
            temporal_scope=temporal_scope,
            timestamp_fields=("create_time", "create_time_warsaw", "timestamp"),
        )
        for archive_hit in archive_hits:
            if not isinstance(archive_hit, dict):
                continue
            content = self._clean(archive_hit.get("excerpt") or archive_hit.get("text"))
            if not content:
                continue
            if not self._source_item_allowed(archive_hit, content=content, user_text=user_text):
                continue
            confidence = self._float_or_none(archive_hit.get("identity_confidence"))
            score, label, assessment = self._assess(content, terms, user_text, confidence=confidence)
            # bm25 rank jest zwykle mniejsze dla lepszych wyników; traktujemy je tylko jako tie-breaker,
            # a nie zamiennik oceny znaczeniowej.
            if archive_hit.get("grounding") == "conversation_archive_v1+fts_v1":
                assessment = "treściowy fragment z conversation_archive/FTS; dobry trop pamięciowy, jeśli odpowiada pytaniu i zachowuje granicę prawdy"
            source_parts = [self._clean(archive_hit.get("source_name")), self._clean(archive_hit.get("source_locator"))]
            source = " / ".join(x for x in source_parts if x) or "conversation_archive_v1"
            title = self._clean(archive_hit.get("conversation_title"))
            role = self._clean(archive_hit.get("author_role"))
            if title or role:
                source = f"{source} / {title or 'bez tytułu'} / {role or 'unknown'}"
            items.append(MemoryRecallItem(
                item_type="conversation_archive",
                query_term=self._first_matching_term(content, terms) or archive_hit.get("phrase"),
                timestamp=self._clean(archive_hit.get("create_time_warsaw")),
                source=source,
                confidence=confidence,
                grounding="conversation_archive_v1+fts_v1",
                relevance_score=score,
                relevance_label=label,
                meaning_assessment=assessment,
                content_excerpt=self._excerpt(content, max_len=460),
                truth_status=self._clean(archive_hit.get("truth_status")) or "source_recorded",
                metadata={
                    "author_role": role,
                    "conversation_title": title,
                    "source_locator": self._clean(archive_hit.get("source_locator")),
                },
            ))

        raw_chat_hits = self.filter_temporal_candidates(
            memory_context.get("raw_chat_fallback") or [],
            temporal_scope=temporal_scope,
            timestamp_fields=("timestamp", "create_time"),
        )
        for raw in raw_chat_hits:
            if not isinstance(raw, dict):
                continue
            content = self._clean(raw.get("snippet"))
            if not content:
                continue
            if not self._source_item_allowed(raw, content=content, user_text=user_text):
                continue
            score, label, assessment = self._assess(content, terms, user_text, confidence=None, raw=True)
            items.append(MemoryRecallItem(
                item_type="raw_chat_fallback",
                query_term=self._clean(raw.get("term")) or self._first_matching_term(content, terms),
                timestamp=None,
                source="memory/raw/chat.html fallback scan",
                confidence=None,
                grounding="raw_text_scan_not_full_index",
                relevance_score=score,
                relevance_label=label,
                meaning_assessment=assessment,
                content_excerpt=self._excerpt(content, max_len=360),
                truth_status=self._clean(raw.get("truth_status")) or "source_recorded",
                metadata={"fallback": True},
            ))

        source_policy = build_typed_source_policy(user_text)
        typed_items: list[MemoryRecallItem] = []
        for item in items:
            decision = source_policy.evaluate(
                item_type=item.item_type,
                source=item.source,
                source_layer=str(item.metadata.get("source_layer") or ""),
                grounding=item.grounding,
                path=str(item.metadata.get("path") or item.source or ""),
                metadata=item.metadata,
            )
            if not decision.allowed:
                continue
            item.semantic_source_type = decision.semantic_source_type
            item.provenance_label = decision.provenance_label
            if not item.truth_status:
                item.truth_status = "unknown"
            typed_items.append(item)

        # Ranking jest najpierw zgodny z intencją i typem źródła, dopiero potem
        # z czystą trafnością leksykalną. Dzięki temu kod/procedury nie wygrywają
        # autobiograficznego recallu tylko dlatego, że zawierają te same słowa.
        typed_items.sort(
            key=lambda item: (
                source_policy.priority_for(item.semantic_source_type),
                item.relevance_score,
                item.confidence or 0.0,
            ),
            reverse=True,
        )
        return typed_items[:limit]

    @staticmethod
    def _temporal_scope_from_context(memory_context: Mapping[str, Any]) -> Any:
        plan = memory_context.get("memory_search_plan")
        if not isinstance(plan, Mapping):
            return None
        return plan.get("temporal_scope")

    @classmethod
    def filter_temporal_candidates(
        cls,
        candidates: Any,
        *,
        temporal_scope: Any,
        timestamp_fields: Sequence[str],
    ) -> list[dict[str, Any]]:
        """Apply one half-open temporal boundary before memory reaches NLG.

        A requested scope is fail-closed: a candidate needs one timezone-aware
        ISO timestamp (or a finite Unix epoch) and it must satisfy
        ``start <= timestamp < end``. Timeless source files and malformed
        legacy rows therefore cannot become a dated autobiographical recall.
        """

        values = [dict(item) for item in candidates if isinstance(item, Mapping)]
        if not temporal_scope:
            return values
        bounds = cls._validated_temporal_bounds(temporal_scope)
        if bounds is None:
            return []
        start_epoch, end_epoch_exclusive = bounds
        filtered: list[dict[str, Any]] = []
        for item in values:
            timestamp_value: Any = None
            for field in timestamp_fields:
                candidate = item.get(field)
                if candidate is not None and str(candidate).strip():
                    timestamp_value = candidate
                    break
            timestamp_epoch = cls._verified_timestamp_epoch(timestamp_value)
            if (
                timestamp_epoch is not None
                and start_epoch <= timestamp_epoch < end_epoch_exclusive
            ):
                filtered.append(item)
        return filtered

    @classmethod
    def _validated_temporal_bounds(cls, temporal_scope: Any) -> tuple[float, float] | None:
        if not isinstance(temporal_scope, Mapping):
            return None
        start = cls._finite_epoch(temporal_scope.get("start_epoch"))
        end = cls._finite_epoch(temporal_scope.get("end_epoch_exclusive"))
        if start is None or end is None or start >= end:
            return None
        return start, end

    @classmethod
    def _verified_timestamp_epoch(cls, value: Any) -> float | None:
        numeric = cls._finite_epoch(value)
        if numeric is not None:
            return numeric
        text = str(value or "").strip()
        if not text:
            return None
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except (TypeError, ValueError, OverflowError):
            return None
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return None
        try:
            epoch = parsed.timestamp()
        except (OSError, OverflowError, ValueError):
            return None
        return epoch if math.isfinite(epoch) else None

    @staticmethod
    def _finite_epoch(value: Any) -> float | None:
        if isinstance(value, bool) or value is None:
            return None
        if not isinstance(value, (int, float)):
            return None
        epoch = float(value)
        return epoch if math.isfinite(epoch) else None

    def build_payload(self, memory_context: dict[str, Any] | None, *, user_text: str = "", limit: int = 6) -> dict[str, Any]:
        counts = (memory_context or {}).get("counts") if isinstance(memory_context, dict) else {}
        items = self.build_items(memory_context, user_text=user_text, limit=limit)
        source_policy = build_typed_source_policy(user_text)
        slot_plan = self.build_slot_plan(items, user_text=user_text)
        return {
            "schema_version": "memory_recall_content/v2",
            "query_terms": (memory_context or {}).get("query_terms") if isinstance(memory_context, dict) else [],
            "memory_search_plan": (memory_context or {}).get("memory_search_plan") if isinstance(memory_context, dict) else None,
            "living_memory_search": (memory_context or {}).get("living_memory_search") if isinstance(memory_context, dict) else None,
            "counts": counts or {},
            "source_policy": source_policy.to_dict(),
            "items": [i.to_dict() for i in items],
            "slot_plan": slot_plan,
            "summary": self.summary(items, counts or {}),
            "rule": (
                "typ źródła jest dobierany do intencji; każdy slot ma własne provenance/truth_status; "
                "brak właściwego źródła pozostaje evidence gap zamiast halucynacji"
            ),
        }

    def build_slot_plan(self, items: list[MemoryRecallItem], *, user_text: str) -> dict[str, Any]:
        report = analyse_utterance(user_text)
        requested = list(dict.fromkeys(report.response_slots))
        return MemorySlotSelector().build_slot_plan(items, requested_slots=requested)

    def render(self, memory_context: dict[str, Any] | None, *, user_text: str = "", limit: int = 6) -> str:
        payload = self.build_payload(memory_context, user_text=user_text, limit=limit)
        items = payload["items"]
        counts = payload["counts"]
        terms = payload.get("query_terms") or []
        counts_note = self._counts_text(counts)
        if not items:
            living_value = payload.get("living_memory_search")
            living: dict[str, Any] = living_value if isinstance(living_value, dict) else {}
            living_status = str(living.get("status") or "unknown")
            living_counts_value = living.get("counts")
            living_counts: dict[str, Any] = living_counts_value if isinstance(living_counts_value, dict) else {}
            ready_sources = int(living_counts.get("sources_recall_ready") or 0)
            issues = [str(value) for value in (living.get("issues") or []) if str(value).strip()]
            issue_note = f" Pierwszy błąd źródła: {issues[0]}." if issues else ""
            return (
                f"Szukałam treściowych tropów pamięci po hasłach: {', '.join(map(str, terms)) or 'brak haseł'}. "
                f"Nie znalazłam fragmentów, które mogłabym uczciwie przywołać jako treść wspomnienia. {counts_note} "
                f"Stan pięciu baz: {living_status}; gotowe źródła: {ready_sources}.{issue_note} "
                "W tej sytuacji nie wolno mi udawać przypomnienia tylko dlatego, że istnieje licznik albo indeks."
            ).strip()

        lines = [
            f"Znalazłam treściowe tropy pamięci po hasłach: {', '.join(map(str, terms)) or 'brak haseł'}. {counts_note}".strip(),
            "Najważniejsze ślady, już z treścią i oceną trafności:",
        ]
        for idx, item in enumerate(items, start=1):
            conf = f", pewność={item['confidence']:.2f}" if isinstance(item.get("confidence"), float) else ""
            timestamp = item.get("timestamp") or "czas nieustalony"
            source = item.get("source") or "źródło nieustalone"
            term = item.get("query_term") or "bez osobnego hasła"
            lines.append(
                f"{idx}. {item.get('provenance_label')}: {item['content_excerpt']} "
                f"[typ={item.get('semantic_source_type')}, czas={timestamp}, źródło={source}, "
                f"truth={item.get('truth_status')}{conf}, trafność={item['relevance_label']} "
                f"({item['relevance_score']:.2f}), hasło={term}]"
            )
        lines.append("Wniosek: liczby zostają tylko diagnostyką; właściwe przypomnienie musi pokazać, co zostało znalezione i czy ma sens dla pytania.")
        return "\n".join(lines)

    def summary(self, items: list[MemoryRecallItem], counts: dict[str, Any]) -> str:
        strong = sum(1 for i in items if i.relevance_label == "wysoka")
        medium = sum(1 for i in items if i.relevance_label == "średnia")
        weak = sum(1 for i in items if i.relevance_label == "słaba")
        return f"treściowe_tropy={len(items)}, wysoka={strong}, średnia={medium}, słaba={weak}, counts={counts}"

    @classmethod
    def _assess(
        cls,
        content: str,
        terms: list[str],
        user_text: str,
        *,
        confidence: float | None,
        raw: bool = False,
    ) -> tuple[float, str, str]:
        low = content.lower()
        user_low = (user_text or "").lower()
        technical_query = any(m in user_low for m in cls.TECHNICAL_QUERY_MARKERS)
        norm_low = cls._norm_text(content)
        matched = sum(1 for t in terms if t and (t.lower() in low or cls._norm_text(t) in norm_low))
        score = 0.34 + min(0.28, matched * 0.08)
        if confidence is not None:
            score += max(0.0, min(0.2, confidence * 0.2))
        if raw:
            score -= 0.08
        is_technical = any(m in low for m in cls.TECHNICAL_MARKERS)
        if is_technical and not technical_query:
            score -= 0.18
        if content.strip() and user_text.strip() and cls._similar_prefix(content, user_text):
            score -= 0.1
        score = max(0.0, min(1.0, score))
        if score >= 0.62:
            label = "wysoka"
        elif score >= 0.43:
            label = "średnia"
        else:
            label = "słaba"
        if is_technical and not technical_query:
            assessment = "raczej techniczny albo przypadkowy ślad; wolno go pokazać, ale nie należy udawać osobistego wspomnienia"
        elif raw:
            assessment = "awaryjny fragment z surowego chat.html; wymaga ostrożności, bo nie pochodzi z pełnego indeksu"
        elif label == "wysoka":
            assessment = "znaczeniowo użyteczny trop pamięci, nadaje się do przywołania w odpowiedzi"
        elif label == "średnia":
            assessment = "częściowo użyteczny trop; pokazuje kierunek, ale wymaga granicy prawdy"
        else:
            assessment = "słabe dopasowanie leksykalne; traktować pomocniczo, nie jako główne wspomnienie"
        return score, label, assessment

    @staticmethod
    def _norm_text(text: str) -> str:
        import unicodedata
        text = (text or "").lower()
        text = unicodedata.normalize("NFKD", text)
        text = "".join(ch for ch in text if not unicodedata.combining(ch))
        text = text.replace("ł", "l")
        return re.sub(r"\s+", " ", text).strip()

    @staticmethod
    def _similar_prefix(content: str, user_text: str) -> bool:
        a = re.sub(r"\s+", " ", content.strip().lower())[:120]
        b = re.sub(r"\s+", " ", user_text.strip().lower())[:120]
        return bool(a and b and (a.startswith(b[:40]) or b.startswith(a[:40])))

    @classmethod
    def _source_item_allowed(
        cls,
        item: dict[str, Any],
        *,
        content: str,
        user_text: str,
    ) -> bool:
        truth_status = cls._norm_text(
            str(item.get("truth_status") or item.get("review_status") or "")
        )
        if truth_status in {"rejected", "quarantined", "invalid", "superseded", "untrusted"}:
            return False
        if item.get("identity_confidence") is not None:
            confidence = cls._float_or_none(item.get("identity_confidence"))
            if confidence is None or confidence < 0.5:
                return False
        content_norm = cls._norm_text(content)
        user_norm = cls._norm_text(user_text)
        if not content_norm or not user_norm:
            return True
        if content_norm == user_norm:
            return False
        shorter = min(len(content_norm), len(user_norm))
        longer = max(len(content_norm), len(user_norm))
        if (
            shorter >= 40
            and longer <= int(shorter * 1.35)
            and (content_norm in user_norm or user_norm in content_norm)
        ):
            return False
        return True

    @staticmethod
    def _first_matching_term(content: str, terms: list[str]) -> str | None:
        low = content.lower()
        for term in terms:
            if term and term.lower() in low:
                return term
        return None

    @staticmethod
    def _float_or_none(value: Any) -> float | None:
        try:
            if value is None:
                return None
            return float(value)
        except Exception:
            return None

    @staticmethod
    def _clean(value: Any) -> str | None:
        if value is None:
            return None
        text = re.sub(r"\s+", " ", str(value)).strip()
        return text or None

    @classmethod
    def _excerpt(cls, value: str, max_len: int = 320) -> str:
        text = cls._redact_sensitive_text(re.sub(r"\s+", " ", value).strip())
        if len(text) <= max_len:
            return text
        return text[: max_len - 1].rstrip() + "…"

    @staticmethod
    def _redact_sensitive_text(text: str) -> str:
        # Pamięć legacy może zawierać prywatne albo medyczne dane z importów.
        # Warstwa przypominania ma pokazywać sens wspomnienia, nie ujawniać PESEL-i,
        # telefonów, maili ani treści klinicznych znalezionych przypadkowym trafieniem.
        if re.search(r"PESEL|dane kliniczne|pacjent|uraz|diagnoz|badanie kliniczne|charakter urazu", text, flags=re.IGNORECASE):
            return "[FRAGMENT ZAWIERA DANE WRAŻLIWE LUB MEDYCZNE — UKRYTY W ODPOWIEDZI]"
        text = re.sub(r"(?<!\d)\d{11}(?!\d)", "[PESEL/DANE_WRAŻLIWE_UKRYTE]", text)
        text = re.sub(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "[EMAIL_UKRYTY]", text)
        text = re.sub(r"(?<!\d)(?:\+?48[ -]?)?(?:\d[ -]?){9}(?!\d)", "[TELEFON_UKRYTY]", text)
        return text

    @staticmethod
    def _counts_text(counts: dict[str, Any]) -> str:
        if not counts:
            return "Liczniki diagnostyczne: brak."
        parts = []
        for key in ("episodes", "legacy_messages", "source_file_hits", "raw_chat_fallback"):
            val = counts.get(key)
            if isinstance(val, int):
                parts.append(f"{key}={val}")
        return "Liczniki diagnostyczne: " + (", ".join(parts) if parts else str(counts)) + "."
