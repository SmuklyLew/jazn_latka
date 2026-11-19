"""Evidence-only claims about accepted current-session dialogue history.

An absent or rejected turn cannot be promoted into an observed earlier message.
This module is a candidate-validator rule, not a memory source or finalizer.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any


_CANONICAL_SOURCE = "workspace_runtime/conversation_state per-turn accepted records"
_CLAIMS = (
    re.compile(r"\b(?:w|we)\s+(?:zapisanej|utrwalonej)\s+historii\b.{0,100}\b(?:widze|odczyt|znajduj|mam)"),
    re.compile(r"\b(?:widze|odczytalam|pamietam|znalazlam)\b.{0,85}\b(?:poprzedni|poprzednio|wczesniej|historii|zapisie)"),
    re.compile(r"\b(?:poprzednio|wczesniej|ostatnio)\s+(?:zapytales|podales|napisales|powiedziales)\b"),
)
_NEGATED = re.compile(r"\b(?:nie|nigdy)\s+$")


def _fold(value: str) -> str:
    raw = unicodedata.normalize("NFKD", str(value or "").casefold()).replace("ł", "l")
    return "".join(ch for ch in raw if not unicodedata.combining(ch))


def claims_verified_previous_turn(body: str) -> bool:
    """Detect positive claims, not honest absence disclosures."""
    text = _fold(body)
    for pattern in _CLAIMS:
        for match in pattern.finditer(text):
            if _NEGATED.search(text[max(0, match.start() - 12):match.start()]):
                continue
            return True
    return False


def has_runtime_verified_session_source(history: Any) -> bool:
    """Require a runtime-built accepted projection or validated targeted lookup.

    The runtime session owner builds this evidence from durable accepted turns.
    Legacy previous_user_text and model output never authorize history claims.
    """
    if not isinstance(history, dict) or history.get("source_of_truth") != _CANONICAL_SOURCE:
        return False
    turns = history.get("turns")
    if isinstance(turns, list):
        for turn in turns:
            if not isinstance(turn, dict):
                continue
            if (
                str(turn.get("turn_id") or "").strip()
                and str(turn.get("trace_id") or "").strip()
                and str(turn.get("accepted_at_utc") or "").strip()
                and str(turn.get("user_text") or "").strip()
            ):
                return True
    targeted = history.get("targeted_recall")
    if isinstance(targeted, dict) and targeted.get("ok") is True and targeted.get("status") == "found" and targeted.get("source") == "accepted_session_turn_record":
        record = targeted.get("record")
        if isinstance(record, dict) and record.get("session_id") == history.get("session_id"):
            from latka_jazn.core.conversation_state_store import ConversationStateStore
            checked, error = ConversationStateStore._validate_payload(record)
            return checked is not None and error is None
    return False
