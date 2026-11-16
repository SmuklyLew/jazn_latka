"""Exact, source-verified quotations from an accepted current-session turn.

Never rewrite canonical turns or claim a quote from a missing/corrupt record.
The model and host still pass through the regular Jaźń turn validators.
"""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Any

from latka_jazn.core.conversation_state_store import ConversationStateStore
from latka_jazn.core.message_envelope import strip_recognized_visible_envelope


_WORD_COUNTS = {
    "jeden": 1, "jedno": 1, "jedna": 1,
    "dwa": 2, "dwoch": 2, "trzy": 3, "trzech": 3,
    "cztery": 4, "czterech": 4, "piec": 5, "pieciu": 5,
    "szesc": 6, "szesciu": 6, "siedem": 7, "siedmiu": 7,
    "osiem": 8, "osmiu": 8, "dziewiec": 9, "dziewieciu": 9,
    "dziesiec": 10, "dziesieciu": 10,
}
_ANCHOR = re.compile(
    r"\b(?P<position>pierwsz\w*|ostatni\w*|poprzedni\w*)\s+"
    r"(?P<kind>odpowiedz\w*|wypowiedz\w*|wiadomosc\w*)\b"
)
_FIRST_WORDS = re.compile(r"\bpierwsz\w*\s+(?P<count>\d{1,2}|[a-z]+)\s+slow\w*\b")
_LAST_SENTENCE = re.compile(r"\bostatni\w*\s+zdani\w*\b")
_REQUEST = re.compile(r"\b(?:zacytuj|cytuj|podaj|napisz|przypomnij|przywolaj|jak brzmial\w*|jakie byly)\b")
_CROSS_SESSION = re.compile(
    r"\b(?:wczoraj\w*|przedwczoraj\w*|sprzed|tydzien\w*|miesiac\w*|"
    r"inna sesja|innej sesji|innym czacie|poprzednim czacie|"
    r"wczesniejszej sesji)\b|\b(?:19|20)\d{2}\b"
)


def _fold(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or "").casefold()).replace("ł", "l")
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", normalized)).strip()


def parse_exact_session_quote_request(text: str) -> dict[str, Any] | None:
    """Recognize bounded explicit Polish literal-quote requests only."""
    folded = _fold(text)
    if not folded or _CROSS_SESSION.search(folded) or not _REQUEST.search(folded):
        return None
    anchor = _ANCHOR.search(folded)
    if anchor is None:
        return None
    first = _FIRST_WORDS.search(folded)
    last_sentence = _LAST_SENTENCE.search(folded)
    if bool(first) == bool(last_sentence):
        return None
    kind = anchor.group("kind")
    role = "assistant" if kind.startswith(("odpowiedz", "wypowiedz")) else "user"
    # "moja poprzednia wiadomość" is a user turn, "twoja/swoja odpowiedź" is assistant.
    before = folded[:anchor.start()]
    if kind.startswith("wiadomosc") and re.search(r"\b(?:twoj\w*|swoj\w*)\b", before):
        role = "assistant"
    selector = "first" if anchor.group("position").startswith("pierwsz") else "last"
    if first:
        token = first.group("count")
        count = int(token) if token.isdecimal() else _WORD_COUNTS.get(token)
        if count is None or not 1 <= count <= 50:
            return None
        fragment = "first_words"
    else:
        count = None
        fragment = "last_sentence"
    return {"selector": selector, "role": role, "fragment": fragment, "count": count}


def exact_quote_from_accepted_turn(
    root: Path, session_id: str, text: str,
) -> dict[str, Any] | None:
    """Read and verify a canonical record anew; never trust supplied model context."""
    request = parse_exact_session_quote_request(text)
    if request is None:
        return None
    if not str(session_id or "").strip():
        return {"ok": False, "status": "session_unavailable", "request": request}
    store = ConversationStateStore(Path(root))
    try:
        lookup = store.lookup_accepted_turn(session_id, selector=request["selector"])
    except (OSError, ValueError):
        return {"ok": False, "status": "integrity_error", "request": request}
    if (lookup.get("ok") is not True or lookup.get("status") != "found"
            or lookup.get("source") != "accepted_session_turn_record"
            or lookup.get("session_id") != session_id):
        return {"ok": False, "status": str(lookup.get("status") or "unavailable"), "request": request}
    record = lookup["record"]
    raw = str(record["assistant_text"] if request["role"] == "assistant" else record["user_text"])
    body = strip_recognized_visible_envelope(raw) if request["role"] == "assistant" else raw
    if request["fragment"] == "first_words":
        words = body.split()
        count = request["count"]
        if len(words) < count:
            return {"ok": False, "status": "fragment_unavailable", "request": request}
        fragment = " ".join(words[:count])
    else:
        sentences = [part.strip() for part in re.findall(r"[^.!?]+(?:[.!?]+|$)", body) if part.strip()]
        if not sentences:
            return {"ok": False, "status": "fragment_unavailable", "request": request}
        fragment = sentences[-1]
    if not fragment:
        return {"ok": False, "status": "fragment_unavailable", "request": request}
    return {
        "ok": True, "status": "found", "request": request, "text": fragment,
        "turn_id": str(record["turn_id"]), "trace_id": str(record["trace_id"]),
        "record_sha256": str(record.get("record_sha256") or ""),
        "source": "accepted_session_turn_record",
    }
