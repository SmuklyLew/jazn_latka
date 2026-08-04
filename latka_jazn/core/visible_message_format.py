from __future__ import annotations

"""Canonical presentation rules for visible Jaźń messages.

This module is the single source of truth for the user-visible message shape:

    🕒 [YYYY-MM-DD HH:MM]
    <state emoticon> <author label>

    <body>

When no wall clock can be obtained from the execution environment or the
network fallback, the first line is rendered as ``🕒 [ZEGAR NIEDOSTĘPNY]``.
Clock quality is metadata only and must never decide whether the body may be
shown.  Other modules may validate identity, provenance and body integrity,
but must delegate visible envelope rendering and parsing to this file.

The legacy second-precision header remains accepted for stored records and
in-flight compatibility, but it is never emitted by the canonical renderer.
"""

from datetime import datetime
import re

CLOCK_ICON = "🕒"
CLOCK_UNAVAILABLE_LABEL = "ZEGAR NIEDOSTĘPNY"
CLOCK_UNAVAILABLE_HEADER = f"{CLOCK_ICON} [{CLOCK_UNAVAILABLE_LABEL}]"
VISIBLE_TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M"
LEGACY_TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"

AVAILABLE_CLOCK_HEADER_RE = re.compile(
    r"^🕒 \[(?P<value>\d{4}-\d{2}-\d{2} \d{2}:\d{2})\]$"
)
LEGACY_CLOCK_HEADER_RE = re.compile(
    r"^🕒 (?P<value>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})$"
)
CLOCK_HEADER_RE = re.compile(
    r"^(?:🕒 \[(?:\d{4}-\d{2}-\d{2} \d{2}:\d{2}|ZEGAR NIEDOSTĘPNY)\]|"
    r"🕒 \d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})$"
)

VISIBLE_MESSAGE_FORMAT_RULE = (
    "Visible Jaźń messages are rendered only by "
    "latka_jazn.core.visible_message_format. Clock unavailability changes "
    "only the first line to '🕒 [ZEGAR NIEDOSTĘPNY]' and never blocks the body."
)


def normalize_newlines(value: str | None) -> str:
    return str(value or "").replace("\r\n", "\n").replace("\r", "\n")


def render_clock_header(local_dt: datetime | None) -> str:
    """Render the canonical clock line without inventing a wall-clock value."""
    if local_dt is None:
        return CLOCK_UNAVAILABLE_HEADER
    if local_dt.tzinfo is None:
        raise ValueError("clock datetime must be timezone-aware")
    return f"{CLOCK_ICON} [{local_dt:{VISIBLE_TIMESTAMP_FORMAT}}]"


def is_clock_unavailable_header(header: str | None) -> bool:
    return str(header or "").strip() == CLOCK_UNAVAILABLE_HEADER


def is_recognized_clock_header(header: str | None) -> bool:
    return bool(CLOCK_HEADER_RE.fullmatch(str(header or "").strip()))


def parse_clock_header(header: str | None) -> datetime | None:
    """Parse available clock headers; unavailable or malformed headers return None."""
    value = str(header or "").strip()
    match = AVAILABLE_CLOCK_HEADER_RE.fullmatch(value)
    if match:
        try:
            return datetime.strptime(match.group("value"), VISIBLE_TIMESTAMP_FORMAT)
        except ValueError:
            return None
    legacy = LEGACY_CLOCK_HEADER_RE.fullmatch(value)
    if legacy:
        try:
            return datetime.strptime(legacy.group("value"), LEGACY_TIMESTAMP_FORMAT)
        except ValueError:
            return None
    return None


def clock_header_matches_datetime(header: str | None, local_dt: datetime) -> bool:
    """Compare a header with local time at the precision encoded by that header."""
    value = str(header or "").strip()
    parsed = parse_clock_header(value)
    if parsed is None:
        return False
    expected = local_dt.replace(tzinfo=None, microsecond=0)
    if AVAILABLE_CLOCK_HEADER_RE.fullmatch(value):
        expected = expected.replace(second=0)
    return parsed == expected


def render_visible_message(
    *,
    clock_header: str,
    state_emoticon: str,
    author_label: str,
    body: str,
) -> str:
    """Render the canonical visible envelope around a non-empty body."""
    header = str(clock_header or "").strip()
    marker = str(state_emoticon or "").strip()
    author = str(author_label or "").strip()
    normalized_body = normalize_newlines(body)
    if not is_recognized_clock_header(header):
        raise ValueError("clock_header has invalid shape")
    if not marker:
        raise ValueError("state_emoticon is required")
    if not author:
        raise ValueError("author_label is required")
    if not normalized_body.strip():
        raise ValueError("message body is required")
    return f"{header}\n{marker} {author}\n\n{normalized_body}"


def extract_visible_body(
    text: str,
    *,
    clock_header: str,
    state_emoticon: str,
    author_label: str,
) -> str | None:
    value = normalize_newlines(text)
    prefix = f"{clock_header}\n{state_emoticon} {author_label}\n\n"
    if not value.startswith(prefix):
        return None
    return value[len(prefix):]


def strip_visible_message_envelope(text: str) -> str:
    value = normalize_newlines(text).strip()
    lines = value.split("\n")
    if (
        len(lines) >= 4
        and is_recognized_clock_header(lines[0].strip())
        and lines[1].strip()
        and not lines[2].strip()
    ):
        return "\n".join(lines[3:]).strip()
    return value
