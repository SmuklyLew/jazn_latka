from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Mapping
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from latka_jazn.core.visible_message_format import (
    CLOCK_HEADER_RE,
    CLOCK_UNAVAILABLE_HEADER,
    clock_header_matches_datetime,
    extract_visible_body,
    is_clock_unavailable_header,
    normalize_newlines,
    parse_clock_header,
    render_clock_header,
    render_visible_message,
    strip_visible_message_envelope,
)
from latka_jazn.version import schema_version

SCHEMA_VERSION = schema_version("message_envelope")

# Compatibility exports.  New code should import presentation primitives from
# visible_message_format.py, the canonical source for visible message shape.
TIMESTAMP_HEADER_RE = CLOCK_HEADER_RE
render_timestamp_header = render_clock_header
parse_timestamp_header = parse_clock_header


def resolve_author(decision: Mapping[str, Any] | None) -> tuple[str, str, str]:
    payload = dict(decision or {})
    voice = payload.get("voice_source_contract")
    voice = dict(voice) if isinstance(voice, Mapping) else {}
    author_label = str(payload.get("author_label") or voice.get("speaking_identity") or "").strip()
    author_source = str(payload.get("author_source") or voice.get("active_source") or "").strip()
    author_id = str(payload.get("author_id") or ("latka_runtime" if author_source == "jazn_runtime" else "")).strip()
    if not author_id or not author_label or not author_source:
        raise ValueError("verified author_id, author_label and author_source are required")
    if author_label == "Łatka" and author_source != "jazn_runtime":
        raise ValueError("Łatka author label requires jazn_runtime source")
    return author_id, author_label, author_source


@dataclass(slots=True, frozen=True)
class MessageEnvelope:
    timestamp_header: str
    timezone: str
    timestamp_sample_iso: str | None
    timestamp_source: str
    timestamp_trusted: bool
    author_id: str
    author_label: str
    author_source: str
    state_emoticon: str
    body: str
    schema_version: str = SCHEMA_VERSION

    @classmethod
    def build(
        cls,
        *,
        timestamp_header: str,
        timezone: str,
        timestamp_sample_iso: str | None,
        timestamp_source: str | None,
        timestamp_trusted: bool,
        author_id: str,
        author_label: str,
        author_source: str,
        state_emoticon: str,
        body: str,
    ) -> "MessageEnvelope":
        normalized_body = normalize_newlines(body)
        if not normalized_body.strip():
            raise ValueError("message body is required")
        header = str(timestamp_header or "").strip()
        if not TIMESTAMP_HEADER_RE.fullmatch(header):
            raise ValueError("timestamp header has invalid shape")
        unavailable = is_clock_unavailable_header(header)
        timezone_value = str(timezone or "").strip()
        sample_value = str(timestamp_sample_iso or "").strip() or None
        source_value = str(timestamp_source or "").strip()
        if unavailable:
            timezone_value = timezone_value or "Europe/Warsaw"
            source_value = source_value or "unavailable"
            sample_value = None
            timestamp_trusted = False
        else:
            if not timezone_value:
                raise ValueError("timezone is required")
            if sample_value is None:
                raise ValueError("timestamp_sample_iso is required for an available clock")
            if not source_value:
                raise ValueError("timestamp_source is required for an available clock")
        if not str(author_id or "").strip() or not str(author_label or "").strip() or not str(author_source or "").strip():
            raise ValueError("verified author metadata is required")
        if not str(state_emoticon or "").strip():
            raise ValueError("state_emoticon is required; unknown affect must be explicit")
        return cls(
            timestamp_header=header,
            timezone=timezone_value,
            timestamp_sample_iso=sample_value,
            timestamp_source=source_value,
            timestamp_trusted=bool(timestamp_trusted),
            author_id=str(author_id).strip(),
            author_label=str(author_label).strip(),
            author_source=str(author_source).strip(),
            state_emoticon=str(state_emoticon).strip(),
            body=normalized_body,
        )

    @property
    def clock_available(self) -> bool:
        return not is_clock_unavailable_header(self.timestamp_header)

    def render(self) -> str:
        return render_visible_message(
            clock_header=self.timestamp_header,
            state_emoticon=self.state_emoticon,
            author_label=self.author_label,
            body=self.body,
        )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["clock_available"] = self.clock_available
        return payload

    def timestamp_matches_sample(self) -> bool:
        if not self.clock_available:
            return self.timestamp_sample_iso is None
        try:
            sample = datetime.fromisoformat(str(self.timestamp_sample_iso).replace("Z", "+00:00"))
            if sample.tzinfo is None:
                return False
            zone = ZoneInfo(self.timezone)
        except (ValueError, ZoneInfoNotFoundError):
            return False
        return clock_header_matches_datetime(self.timestamp_header, sample.astimezone(zone))


def extract_body_from_visible_text(
    text: str,
    *,
    timestamp_header: str,
    state_emoticon: str,
    author_label: str,
) -> str | None:
    return extract_visible_body(
        text,
        clock_header=timestamp_header,
        state_emoticon=state_emoticon,
        author_label=author_label,
    )


def strip_recognized_visible_envelope(text: str) -> str:
    return strip_visible_message_envelope(text)


__all__ = [
    "CLOCK_UNAVAILABLE_HEADER",
    "MessageEnvelope",
    "TIMESTAMP_HEADER_RE",
    "extract_body_from_visible_text",
    "normalize_newlines",
    "parse_timestamp_header",
    "render_timestamp_header",
    "resolve_author",
    "strip_recognized_visible_envelope",
]
