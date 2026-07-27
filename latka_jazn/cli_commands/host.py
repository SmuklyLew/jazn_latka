from __future__ import annotations

from typing import Any

from latka_jazn.core.host_visible_finalization import finalize_host_visible_text


def finalize_payload(args: Any) -> dict[str, Any]:
    text = args.text
    if args.text_file:
        text = args.text_file.read_text(encoding="utf-8-sig")
    result = finalize_host_visible_text(
        required_timestamp_header=args.timestamp_header,
        timezone=args.timezone,
        timestamp_sample_iso=args.timestamp_sample_iso,
        timestamp_source=args.timestamp_source,
        timestamp_trusted=args.timestamp_trusted,
        author_id=args.author_id,
        author_label=args.author_label,
        author_source=args.author_source,
        state_emoticon=args.state_emoticon,
        turn_id=args.turn_id,
        trace_id=args.trace_id,
        text=text,
        supplied_turn_id=args.supplied_turn_id,
        supplied_trace_id=args.supplied_trace_id,
        supplied_text_sha256=args.text_sha256,
        max_utf8_bytes=args.max_bytes,
    )
    return result.to_dict()
