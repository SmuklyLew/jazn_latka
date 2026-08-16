from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping
import hashlib

from latka_jazn.core.epistemic_claim_guard import EpistemicClaimGuard
from latka_jazn.core.message_envelope import MessageEnvelope, normalize_newlines
from latka_jazn.version import schema_version

SCHEMA_VERSION = schema_version("final_visible_reply_capture")


def _sha(value: str) -> str:
    return hashlib.sha256(normalize_newlines(value).encode("utf-8")).hexdigest()


@dataclass(slots=True)
class FinalVisibleReplyCapture:
    turn_id: str
    trace_id: str
    timestamp_header: str
    timezone: str
    timestamp_sample_iso: str
    timestamp_source: str
    timestamp_trusted: bool
    author_id: str
    author_label: str
    author_source: str
    state_emoticon: str
    source: str
    original_text_sha256: str
    final_text_sha256: str
    envelope_present_in_original: bool
    envelope_present_in_final: bool
    was_rendered_from_body: bool
    final_visible_text: str
    epistemic_claims: list[dict[str, Any]] = field(default_factory=list)
    schema_version: str = SCHEMA_VERSION

    @classmethod
    def build(
        cls,
        *,
        turn_id: str,
        trace_id: str,
        timestamp_header: str,
        timezone: str,
        timestamp_sample_iso: str,
        timestamp_source: str,
        timestamp_trusted: bool,
        author_id: str,
        author_label: str,
        author_source: str,
        state_emoticon: str,
        final_text: str,
        source: str = "chatgpt_visible_layer",
        epistemic_evidence: Mapping[str, Any] | None = None,
    ) -> "FinalVisibleReplyCapture":
        if not turn_id or not trace_id:
            raise ValueError("turn_id and trace_id are required")
        original = normalize_newlines(final_text)
        claim_assessments = EpistemicClaimGuard().enforce(
            original,
            evidence=epistemic_evidence,
        )
        envelope = MessageEnvelope.build(
            timestamp_header=timestamp_header,
            timezone=timezone,
            timestamp_sample_iso=timestamp_sample_iso,
            timestamp_source=timestamp_source,
            timestamp_trusted=timestamp_trusted,
            author_id=author_id,
            author_label=author_label,
            author_source=author_source,
            state_emoticon=state_emoticon,
            body="capture-validation",
        )
        prefix = f"{timestamp_header}\n{state_emoticon} {author_label}\n\n"
        original_has_envelope = original.startswith(prefix)
        if original_has_envelope:
            final_visible_text = original
            rendered = False
        else:
            if original.startswith(timestamp_header) or original.split("\n", 1)[0].startswith("🕒 "):
                raise ValueError("partial or foreign message envelope cannot be repaired")
            final_visible_text = MessageEnvelope.build(
                timestamp_header=timestamp_header,
                timezone=timezone,
                timestamp_sample_iso=timestamp_sample_iso,
                timestamp_source=timestamp_source,
                timestamp_trusted=timestamp_trusted,
                author_id=author_id,
                author_label=author_label,
                author_source=author_source,
                state_emoticon=state_emoticon,
                body=original,
            ).render()
            rendered = True
        if not envelope.timestamp_matches_sample():
            raise ValueError("timestamp header does not match timestamp sample")
        return cls(
            turn_id=turn_id,
            trace_id=trace_id,
            timestamp_header=timestamp_header,
            timezone=timezone,
            timestamp_sample_iso=timestamp_sample_iso,
            timestamp_source=timestamp_source,
            timestamp_trusted=timestamp_trusted,
            author_id=author_id,
            author_label=author_label,
            author_source=author_source,
            state_emoticon=state_emoticon,
            source=source,
            original_text_sha256=_sha(original),
            final_text_sha256=_sha(final_visible_text),
            envelope_present_in_original=original_has_envelope,
            envelope_present_in_final=True,
            was_rendered_from_body=rendered,
            final_visible_text=final_visible_text,
            epistemic_claims=[item.to_dict() for item in claim_assessments],
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
