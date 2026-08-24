from __future__ import annotations

from typing import Any

from latka_jazn.core.memory_intent_contract import MEMORY_EXPERIENCE_INTENTS
from latka_jazn.core.route_handler_base import RouteHandlerResult
from latka_jazn.version import schema_version


SCHEMA_VERSION = schema_version("memory_experience_recall_handler")


class MemoryExperienceRecallHandler:
    """Render experience recall only from the payload sealed by retrieval."""

    name = "MemoryExperienceRecallHandler"
    route = "memory_experience_recall"
    handled_intents = tuple(sorted(MEMORY_EXPERIENCE_INTENTS))

    @staticmethod
    def _clean(value: Any, *, limit: int) -> str:
        return " ".join(str(value or "").split())[:limit]

    @classmethod
    def _normalize(cls, value: Any) -> str:
        return cls._clean(value, limit=2_000).lower().translate(
            str.maketrans("ąćęłńóśźż", "acelnoszz")
        )

    @staticmethod
    def _frozen_payload(context: dict[str, Any]) -> dict[str, Any]:
        memory_value = context.get("memory_context")
        memory_context = memory_value if isinstance(memory_value, dict) else {}
        payload_value = memory_context.get("memory_recall_payload")
        return payload_value if isinstance(payload_value, dict) else {}

    @classmethod
    def _grounded_items(
        cls,
        payload: dict[str, Any],
        *,
        user_text: str,
        limit: int = 3,
    ) -> list[dict[str, Any]]:
        raw_items = payload.get("items")
        source_items = raw_items if isinstance(raw_items, list) else []
        normalized_user = cls._normalize(user_text)
        seen: set[tuple[str, str]] = set()
        items: list[dict[str, Any]] = []
        for raw in source_items:
            if not isinstance(raw, dict):
                continue
            excerpt = cls._clean(
                raw.get("content_excerpt")
                or raw.get("excerpt")
                or raw.get("content"),
                limit=520,
            )
            source = cls._clean(
                raw.get("source")
                or raw.get("source_locator")
                or raw.get("source_type"),
                limit=320,
            )
            if not excerpt or not source:
                continue
            normalized_excerpt = cls._normalize(excerpt)
            if normalized_user and (
                normalized_excerpt == normalized_user
                or (
                    len(normalized_user) >= 24
                    and (
                        normalized_excerpt.startswith(normalized_user)
                        or normalized_user.startswith(normalized_excerpt)
                    )
                )
            ):
                continue
            signature = (cls._normalize(source), normalized_excerpt)
            if signature in seen:
                continue
            seen.add(signature)
            confidence_value = raw.get("confidence")
            confidence = (
                float(confidence_value)
                if isinstance(confidence_value, (int, float))
                and not isinstance(confidence_value, bool)
                else None
            )
            items.append(
                {
                    "item_id": cls._clean(
                        raw.get("item_id") or raw.get("record_id"),
                        limit=160,
                    )
                    or None,
                    "content_excerpt": excerpt,
                    "source": source,
                    "timestamp": cls._clean(
                        raw.get("timestamp") or raw.get("created_at"),
                        limit=160,
                    )
                    or None,
                    "grounding": cls._clean(raw.get("grounding"), limit=160)
                    or None,
                    "confidence": confidence,
                }
            )
            if len(items) >= max(1, min(limit, 6)):
                break
        return items

    @staticmethod
    def _render(items: list[dict[str, Any]]) -> str:
        lines = [
            "Z przywołanej pamięci mogę uczciwie oprzeć odpowiedź tylko na tych źródłowych śladach:"
        ]
        for index, item in enumerate(items, start=1):
            timestamp = item.get("timestamp") or "czas nieustalony"
            lines.append(
                f"{index}. {timestamp}: „{item['content_excerpt']}” "
                f"Źródło: {item['source']}."
            )
        lines.append(
            "To są wybrane, źródłowo uziemione fragmenty dopuszczone do odpowiedzi w tej turze. "
            "Jeśli pytasz o szczegół, którego w tych fragmentach nie ma, "
            "nie dopowiem go jako wspomnienia."
        )
        return chr(10).join(lines)

    def handle(
        self,
        text: str,
        context: dict[str, Any] | None = None,
    ) -> RouteHandlerResult:
        ctx = context or {}
        payload = self._frozen_payload(ctx)
        items = self._grounded_items(payload, user_text=text)
        if items:
            body = self._render(items)
            status = "grounded_payload_rendered"
            confidence = 0.86
        else:
            body = (
                "Nie dostałam w tej turze żadnego źródłowo uziemionego "
                "fragmentu pamięci, więc nie mogę uczciwie wygenerować "
                "wspomnienia. Nie zastąpię braku wyniku bieżącą wiadomością, "
                "domysłem ani fikcyjną sceną."
            )
            status = "grounded_payload_empty"
            confidence = 0.72
        return RouteHandlerResult(
            self.name,
            self.route,
            body,
            intent=str(ctx.get("intent") or "memory_experience_question"),
            data={
                "memory_recall_payload": payload,
                "memory_recall_payload_frozen": True,
                "filtered_item_count": len(items),
                "status": status,
                "preserve_handler_body": True,
            },
            memory_sources=items,
            required_components=list(ctx.get("required_components") or []),
            satisfied_components=[
                "memory_content",
                "source_or_index_status",
                "truth_boundary",
                "no_current_turn_echo",
            ],
            confidence=confidence,
            source_origin_detail=SCHEMA_VERSION,
            truth_boundary=(
                "Odpowiedź doświadczeniowa może użyć wyłącznie zamrożonego "
                "memory_recall_payload z bieżącej tury. Pusty lub nieuziemiony "
                "payload kończy się jawnym brakiem wspomnienia."
            ),
        )
