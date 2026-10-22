"""Bounded object frames from public JSONL and structured startup diagnostics."""
from __future__ import annotations

import json
from typing import Any, Iterator, Protocol

MAX_FRAME = 2097152


class FrameStream(Protocol):
    def readline(self, size: int = -1, /) -> bytes: ...


def frames(stream: FrameStream) -> Iterator[dict[str, Any]]:
    pending = bytearray()
    while True:
        line = stream.readline(MAX_FRAME + 1)
        if not line:
            if pending.strip():
                raise ValueError("chat_protocol_incomplete")
            return
        pending.extend(line)
        if len(pending) > MAX_FRAME:
            raise ValueError("chat_output_limit")
        if not pending.strip():
            pending.clear()
            continue
        if not pending.lstrip().startswith(b"{"):
            raise ValueError("chat_protocol_shape")
        try:
            value = json.loads(pending)
        except json.JSONDecodeError:
            # main.py may format a startup rejection over several lines.
            # Never strip a prefix or interpret those bytes as visible speech.
            continue
        if not isinstance(value, dict):
            raise ValueError("chat_protocol_shape")
        yield value
        pending.clear()
