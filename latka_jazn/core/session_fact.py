"""Bounded literal facts from declarative statements in accepted session turns."""
from __future__ import annotations

import re
from typing import Any

from latka_jazn.core.message_envelope import strip_recognized_visible_envelope


# Restrict deterministic extraction to questions about a single named field.
# A field with a qualifier ("nazwa projektu" vs "nazwa miasta") is distinct.
_FIELD = r"(?:nazw[aę]|hasł[oa]|kod|numer|liczb[ęa]|termin|kolor|miejsce)"
_QUERY = re.compile(
    rf"(?:jak(?:i|ą|ie|iego)|któr(?:y|ą|e))\s+(?P<field>{_FIELD}(?:\s+\w+){{0,3}}?)\s+"
    r"(?:ci\s+)?(?:wcześniej\s+|przed chwilą\s+)?"
    r"(?P<verb>(?:poda|napisa|wymieni|zaproponowa|wybra|ustali)ł(?:am|em|aś|eś|iśmy|yśmy))"
    r"(?:\s+(?:wcześniej|w tej rozmowie|w tej sesji))?\s*[?.!]?", re.I,
)
_REMINDER = re.compile(
    rf"(?:przypomnij(?: mi)?|podaj) (?:moj[ąe] )?(?P<field>{_FIELD}(?: [\w-]+){{0,3}}?)"
    r"(?: (?:zapisane|podan[ąey]|ustalon[ąey]))? (?:z tej (?:rozmowy|sesji)|w tej (?:rozmowie|sesji))[.?!]?", re.I,
)
_FORMAT = re.compile(r"(?:odpowiedz|podaj|napisz) (?:tylko|sam[ąo]) (?:liczb[ąę]|nazw[ąę]|hasł(?:o|em)|kod(?:em)?)[.!]?$", re.I)
_CONDITION = re.compile(
    r"(?:jeżeli|jeśli|gdy) nie pamiętasz[, ]+(?:to )?(?:powiedz|napisz|odpowiedz)"
    r"[\s,:„\"']+nie pamiętam[”\"'.! ]*$", re.I,
)
_NOMINATIVE = {"nazwę": "nazwa", "liczbę": "liczba", "hasła": "hasło"}
UNKNOWN = "Nie mam jednoznacznego zapisu tej informacji w tej sesji."
CONFLICT = "W tej sesji padły różne wartości. Którą wypowiedź masz na myśli?"


def without_conditional_absence(text: str) -> str:
    return _CONDITION.sub("", text.strip()).strip()


def fact_request(text: str) -> tuple[str, str] | None:
    question = without_conditional_absence(text)
    if re.search(r"\b(?:wczoraj\w*|inn(?:ej|ą) sesj\w*|poprzedni\w* czat\w*|sprzed)\b", question, re.I):
        return None
    if re.fullmatch(r"(?:co|jaki pomysł) (?:mi )?(?:wcześniej |przed chwilą )?zaproponowałaś[?.!]?", question, re.I):
        return "propozycja", "assistant"
    question = _FORMAT.sub("", question).strip()
    if re.fullmatch(r"co (?:wcześniej |w tej rozmowie )?(?:ustaliliśmy|postanowiliśmy)[?.!]?", question, re.I):
        return "ustalenie", "user"
    match = _QUERY.fullmatch(question) or _REMINDER.fullmatch(question)
    if not match:
        return None
    words = match["field"].casefold().split()
    words[0] = _NOMINATIVE.get(words[0], words[0])
    role = "assistant" if (match.groupdict().get("verb") or "").casefold().endswith(("aś", "eś")) else "user"
    return " ".join(words), role


def resolve_fact(request: tuple[str, str], records: list[dict[str, Any]]) -> dict[str, Any]:
    field, role = request
    declaration = re.compile(
        rf"(?P<correction>(?:poprawka|korekta)\s*[:,]\s*)?(?:moj[ae]|mój|nasz[ae]?)?\s*{re.escape(field)}"
        r"(?:\s*[:=]\s*|\s+(?:to|jest)\s+)(?P<value>[^?!\r\n]{1,160}?)\.?", re.I,
    )
    candidates: dict[str, tuple[str, dict[str, Any]]] = {}
    for record in records:
        source = str(record.get(f"{role}_text") or "")
        if role == "assistant":
            source = strip_recognized_visible_envelope(source)
        for sentence in re.split(r"(?<=[.!?])\s+|\n", source):
            match = declaration.fullmatch(sentence.strip())
            if not match and field == "propozycja":
                match = re.fullmatch(r"(?P<correction>poprawka:\s*)?(?:proponuję|zaproponowałam)\s+(?P<value>[^.!?\r\n]{1,160})\.?", sentence.strip(), re.I)
            if not match and field == "ustalenie":
                match = re.fullmatch(r"(?P<correction>poprawka:\s*)?(?:ustaliliśmy|postanowiliśmy)(?:,? że)?\s+(?P<value>[^.!?\r\n]{1,160})\.?", sentence.strip(), re.I)
            if match:
                if match["correction"]:
                    candidates.clear()
                value = match["value"].strip()
                candidates[value.casefold()] = (value, record)
    metadata = {"request": {"role": role, "fragment": "field_value"}}
    if len(candidates) != 1:
        return {**metadata, "ok": False, "status": "ambiguous" if candidates else "not_found"}
    value, record = next(iter(candidates.values()))
    return {**metadata, "ok": True, "status": "found", "text": value,
            "source": "accepted_session_turn_record", "turn_id": record["turn_id"],
            "trace_id": record["trace_id"], "record_sha256": record.get("record_sha256")}


def fact_answer(result: dict[str, Any]) -> str:
    if result.get("ok"):
        return str(result["text"])
    return CONFLICT if result.get("status") == "ambiguous" else UNKNOWN
