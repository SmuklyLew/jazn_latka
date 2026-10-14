from __future__ import annotations

"""Bounded, UTF-8 complete-frame output for a host-owned non-blocking pipe.

A failed write never changes the durable result or authorizes replay of a turn.
"""

import os
import time
from typing import TextIO


class HostOutputBackpressureError(TimeoutError):
    """The host did not drain its stdout pipe within the bounded interval."""


def write_host_frame(stream: TextIO, frame: str, *, timeout_seconds: float = 10.0) -> None:
    """Emit a complete frame or fail explicitly; do not silently drop a suffix.

    An in-memory/regular blocking stream keeps TextIO semantics. Non-blocking
    pipes use raw writes to avoid TextIOWrapper's partial-buffered-write traps.
    The host must discard partial frames and retrieve the durable turn by ID.
    """
    try:
        fd = stream.fileno()
        nonblocking = not os.get_blocking(fd)
    except (AttributeError, OSError, ValueError):
        nonblocking = False
        fd = -1
    if not nonblocking:
        stream.write(frame)
        stream.flush()
        return

    # A pre-existing buffered frame must drain before any raw bytes are sent.
    # On backpressure this may itself raise BlockingIOError: fail closed rather
    # than interleave frames, and let the host recover an accepted durable turn.
    try:
        stream.flush()
    except BlockingIOError as exc:
        raise HostOutputBackpressureError("host_stdout_preframe_flush_blocked") from exc
    encoded = frame.encode("utf-8")
    cursor = 0
    deadline = time.monotonic() + max(0.0, timeout_seconds)
    while cursor < len(encoded):
        try:
            written = os.write(fd, encoded[cursor:cursor + 65536])
            if written:
                cursor += written
                continue
        except (BlockingIOError, InterruptedError):
            pass
        if time.monotonic() >= deadline:
            raise HostOutputBackpressureError("host_stdout_backpressure_timeout")
        time.sleep(min(0.01, max(0.0, deadline - time.monotonic())))
