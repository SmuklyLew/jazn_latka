from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Mapping
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import re

from latka_jazn.version import schema_version

SCHEMA_VERSION = schema_version("message_envelope")
TIMESTAMP_HEADER_RE = re.compile(r"^🕒 (?P<value>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})$")


def normalize_newlines(value: str | None) -> str:
    return str(value or "").replace("\r\n", "\n").replace("\r", "\n")


def render_timestamp_header(local_dt: datetime) -> str:
    if local_dt.tzinfo is None:
        raise ValueError("timestamp datetime must be timezone-aware")
    return f"🕒 {local_dt:%Y-%m-%d %H:%M:%S}"


def parse_timestamp_header(header: str) -> datetime | None:
    match = TIMESTAMP_HEADER_RE.fullmatch(str(header or "").strip())
    if not match:
        return None
    try:
        return datetime.strptime(match.group("value"), "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


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
    timestamp_sample_iso: str
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
        timestamp_sample_iso: str,
        timestamp_source: str,
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
        if not TIMESTAMP_HEADER_RE.fullmatch(str(timestamp_header or "").strip()):
            raise ValueError("timestamp header has invalid shape")
        if not str(timezone or "").strip():
            raise ValueError("timezone is required")
        if not str(timestamp_sample_iso or "").strip():
            raise ValueError("timestamp_sample_iso is required")
        if not str(timestamp_source or "").strip():
            raise ValueError("timestamp_source is required")
        if not str(author_id or "").strip() or not str(author_label or "").strip() or not str(author_source or "").strip():
            raise ValueError("verified author metadata is required")
        if not str(state_emoticon or "").strip():
            raise ValueError("state_emoticon is required; unknown affect must be explicit")
        return cls(
            timestamp_header=str(timestamp_header).strip(),
            timezone=str(timezone).strip(),
            timestamp_sample_iso=str(timestamp_sample_iso).strip(),
            timestamp_source=str(timestamp_source).strip(),
            timestamp_trusted=bool(timestamp_trusted),
            author_id=str(author_id).strip(),
            author_label=str(author_label).strip(),
            author_source=str(author_source).strip(),
            state_emoticon=str(state_emoticon).strip(),
            body=normalized_body,
        )

    def render(self) -> str:
        return f"{self.timestamp_header}\n{self.state_emoticon} {self.author_label}\n\n{self.body}"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def timestamp_matches_sample(self) -> bool:
        parsed = parse_timestamp_header(self.timestamp_header)
        if parsed is None:
            return False
        try:
            sample = datetime.fromisoformat(self.timestamp_sample_iso.replace("Z", "+00:00"))
            if sample.tzinfo is None:
                return False
            zone = ZoneInfo(self.timezone)
        except (ValueError, ZoneInfoNotFoundError):
            return False
        expected = sample.astimezone(zone).replace(tzinfo=None, microsecond=0)
        return parsed == expected


def extract_body_from_visible_text(
    text: str,
    *,
    timestamp_header: str,
    state_emoticon: str,
    author_label: str,
) -> str | None:
    value = normalize_newlines(text)
    prefix = f"{timestamp_header}\n{state_emoticon} {author_label}\n\n"
    if not value.startswith(prefix):
        return None
    return value[len(prefix):]

def strip_recognized_visible_envelope(text: str) -> str:
    value = normalize_newlines(text).strip()
    lines = value.split("\n")
    if len(lines) >= 4 and TIMESTAMP_HEADER_RE.fullmatch(lines[0].strip()) and lines[1].strip() and not lines[2].strip():
        return "\n".join(lines[3:]).strip()
    return value
