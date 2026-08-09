from __future__ import annotations

import re

DIACRITIC_MAP = str.maketrans("ąćęłńóśźżĄĆĘŁŃÓŚŹŻ", "acelnoszzACELNOSZZ")

PACKAGE_STRONG_RE = re.compile(
    r"\b(?:pacz\w*|zip\w*|manifest\w*|crc|sha(?:256)?|rozpak\w*|wypak\w*|bootstrap\w*|package\w*)\b",
    re.IGNORECASE | re.UNICODE,
)
ARCHIVE_RE = re.compile(r"\barchiw\w*\b", re.IGNORECASE | re.UNICODE)
CONVERSATION_ARCHIVE_RES = (
    re.compile(r"\barchiw\w*\s+(?:rozm\w*|czat\w*|konwersac\w*|wiadom\w*)\b", re.IGNORECASE | re.UNICODE),
    re.compile(r"\b(?:rozm\w*|czat\w*|konwersac\w*|wiadom\w*)\s+(?:z\s+)?archiw\w*\b", re.IGNORECASE | re.UNICODE),
    re.compile(r"\b(?:histori\w*|chronolog\w*)\b.{0,80}\b(?:rozm\w*|czat\w*|konwersac\w*)\b", re.IGNORECASE | re.UNICODE),
    re.compile(r"\b(?:rozm\w*|czat\w*|konwersac\w*)\s+zrodl\w*\b", re.IGNORECASE | re.UNICODE),
    re.compile(
        r"\bco\s+(?:sie\s+)?(?:wtedy\s+)?dzialo\s+sie\b.{0,100}\b(?:miedzy\s+nami|rozm\w*|czat\w*|konwersac\w*)\b",
        re.IGNORECASE | re.UNICODE,
    ),
    re.compile(
        r"\b(?:miedzy\s+nami|nasz\w*\s+relac\w*)\b.{0,100}\b(?:rozm\w*|czat\w*|konwersac\w*)\b",
        re.IGNORECASE | re.UNICODE,
    ),
)
MEMORY_RECALL_ACTION_RE = re.compile(
    r"\b(?:przejrz\w*|przeszuk\w*|wyszuk\w*|szuk\w*|odtworz\w*|odzysk\w*|przypomn\w*|znajdz\w*|wydobadz\w*)\b",
    re.IGNORECASE | re.UNICODE,
)
MEMORY_RECALL_TARGET_RE = re.compile(
    r"\b(?:pamiet\w*|wspomn\w*|histori\w*|przeszlos\w*|pamietnik\w*|ksiazk\w*|chronolog\w*)\b|\bco\s+(?:sie\s+)?(?:wtedy\s+)?dzialo\s+sie\b|\bmiedzy\s+nami\b",
    re.IGNORECASE | re.UNICODE,
)
STATUS_OPERATION_RES = (
    re.compile(r"\bdzialasz\b", re.IGNORECASE | re.UNICODE),
    re.compile(r"\bczy\s+(?:to\s+)?dziala\b", re.IGNORECASE | re.UNICODE),
    re.compile(r"\b(?:runtime|jazn|latka|system|pacz\w*|generator\w*)\s+dziala\b", re.IGNORECASE | re.UNICODE),
    re.compile(r"\bdziala\s+(?:runtime|jazn|latka|system|pacz\w*|generator\w*)\b", re.IGNORECASE | re.UNICODE),
    re.compile(r"\bdzialanie\s+(?:runtime|systemu|pacz\w*|generator\w*)\b", re.IGNORECASE | re.UNICODE),
)


def fold_text(text: str) -> str:
    return (text or "").translate(DIACRITIC_MAP).lower()


def has_explicit_package_context(text: str) -> bool:
    """Return True only for explicit package/archive-runtime vocabulary.

    A bare ``archiwum`` is deliberately not enough because conversation history is
    also an archive. Package intent requires a stronger companion such as ZIP,
    package, manifest, CRC/SHA, extraction or bootstrap terminology.
    """

    return bool(PACKAGE_STRONG_RE.search(fold_text(text)))


def has_conversation_archive_context(text: str) -> bool:
    folded = fold_text(text)
    return any(pattern.search(folded) for pattern in CONVERSATION_ARCHIVE_RES)


def has_conversation_archive_recall_context(text: str) -> bool:
    """Detect requests to recover conversation history, not archive health checks."""

    folded = fold_text(text)
    if not has_conversation_archive_context(folded):
        return False
    return bool(MEMORY_RECALL_ACTION_RE.search(folded) or MEMORY_RECALL_TARGET_RE.search(folded))


def has_runtime_status_operation_context(text: str) -> bool:
    """Detect operational "działa" forms without matching eventive "działo się"."""

    folded = fold_text(text)
    return any(pattern.search(folded) for pattern in STATUS_OPERATION_RES)


def package_archive_evidence(text: str) -> list[str]:
    folded = fold_text(text)
    return [match.group(0) for match in PACKAGE_STRONG_RE.finditer(folded)][:6]


def conversation_archive_evidence(text: str) -> list[str]:
    folded = fold_text(text)
    evidence: list[str] = []
    for pattern in CONVERSATION_ARCHIVE_RES:
        evidence.extend(match.group(0) for match in pattern.finditer(folded))
    return evidence[:6]
