from __future__ import annotations

from typing import Any

from latka_jazn.core.host_visible_finalization import finalize_host_visible_text


def run(
    *,
    required_timestamp_header: str,
    timezone: str,
    timestamp_sample_iso: str,
    timestamp_source: str,
    timestamp_trusted: bool,
    author_id: str,
    author_label: str,
    author_source: str,
    state_emoticon: str,
    turn_id: str,
    trace_id: str,
    final_text: str,
    final_text_sha256: str,
    supplied_turn_id: str | None = None,
    supplied_trace_id: str | None = None,
) -> dict[str, Any]:
    result = finalize_host_visible_text(
        required_timestamp_header=required_timestamp_header,
        timezone=timezone,
        timestamp_sample_iso=timestamp_sample_iso,
        timestamp_source=timestamp_source,
        timestamp_trusted=timestamp_trusted,
        author_id=author_id,
        author_label=author_label,
        author_source=author_source,
        state_emoticon=state_emoticon,
        turn_id=turn_id,
        trace_id=trace_id,
        text=final_text,
        supplied_turn_id=supplied_turn_id,
        supplied_trace_id=supplied_trace_id,
        supplied_text_sha256=final_text_sha256,
    )
    payload = result.to_dict()
    visible = result.final_visible_text if result.accepted else "Host-visible finalization rejected the reply."
    return {
        "content": [{"type": "text", "text": visible}],
        "structuredContent": payload,
        "_meta": {"violations": [item.to_dict() for item in result.violations]},
        "isError": not result.accepted,
    }
