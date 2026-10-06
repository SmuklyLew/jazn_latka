from __future__ import annotations

from typing import Any
from latka_jazn.core.legacy_conversation import ConversationDecision, LegacyConversationResponder
from latka_jazn.core.route_registry import RouteRegistry


class ConversationResponder(LegacyConversationResponder):
    """Structured canonical candidates, plus an explicit legacy compatibility API.

    The normal turn pipeline calls build_candidate. compose is retained only
    for historical debug callers and compatibility tests, never as a fallback.
    """
    def compose(self, text: str, **kwargs: Any) -> ConversationDecision:
        return super().compose(text, **kwargs)

    @staticmethod
    def build_candidate(text: str, *, classified_intent: str) -> ConversationDecision:
        entry = RouteRegistry().resolve(classified_intent)
        return ConversationDecision(
            route=entry.route, body="", debug_fallback_used=False,
            truth_boundary="Structured candidate only; evidence, language realization and acceptance belong to the turn pipeline.",
            detected_user_intent=entry.intent, substantive_remainder=text,
            direct_answer_required=True, continuity_badge_allowed=False,
            runtime_followup_required=True,
        )
