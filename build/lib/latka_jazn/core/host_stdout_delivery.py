from __future__ import annotations

"""Bounded, loss-detecting stdout delivery for the host JSONL bridge.

A durable commit may precede this transport. A failed send is *not* a
failed finalization and must never cause the caller to regenerate the turn.
Only the exact bytes supplied are emitted (no implicit framing or newline).
"""

import errno
import os
import select
import time
from typing import TextIO


class HostStdoutDeliveryError(OSError):
    """The host did not receive a complete stdout frame."""


def write_complete_stdout(stream: TextIO, text: str, *, timeout_seconds: float = 5.0) -> None:
    """Write every UTF-8 byte or raise; never report an incomplete write as success.

    OS descriptors are switched to nonblocking temporarily and restored in a
    finally block. This prevents unbounded blocking when the host stops reading
    its pipe. StringIO/test streams are supported without assuming fileno().
    """
    if timeout_seconds <= 0:
        raise ValueError("stdout delivery timeout must be positive")
    deadline = time.monotonic() + timeout_seconds
    try:
        fd = stream.fileno()
        original_blocking = os.get_blocking(fd)
    except (AttributeError, OSError, ValueError):
        # Includes in-memory streams: preserve their text encoding semantics.
        offset = 0
        while offset < len(text):
            if time.monotonic() >= deadline:
                raise HostStdoutDeliveryError("host_stdout_delivery_timeout")
            try:
                written = stream.write(text[offset:])
            except BlockingIOError:
                time.sleep(min(0.01, max(0.0, deadline - time.monotonic())))
                continue
            if not isinstance(written, int) or written <= 0:
                raise HostStdoutDeliveryError("host_stdout_delivery_no_progress")
            offset += written
        stream.flush()
        return

    payload = text.encode("utf-8")
    # Flush any prior buffered text before writing directly to the descriptor.
    # Failure here is a transport failure, not a reason to replay generation.
    try:
        stream.flush()
        os.set_blocking(fd, False)
    except (OSError, ValueError) as exc:
        raise HostStdoutDeliveryError("host_stdout_delivery_configuration_failed") from exc
    offset = 0
    try:
        while offset < len(payload):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise HostStdoutDeliveryError("host_stdout_delivery_timeout")
            try:
                written = os.write(fd, payload[offset : offset + 65536])
            except InterruptedError:
                continue
            except BlockingIOError:
                written = 0
            except OSError as exc:
                if exc.errno not in (errno.EAGAIN, errno.EWOULDBLOCK):
                    raise HostStdoutDeliveryError("host_stdout_delivery_broken") from exc
                written = 0
            if written:
                offset += written
                continue
            # select supports POSIX pipe descriptors. Windows select may reject
            # non-sockets; use a bounded backoff there instead of spinning.
            if os.name != "nt":
                try:
                    select.select([], [fd], [], min(remaining, 0.10))
                    continue
                except (OSError, ValueError):
                    pass
            time.sleep(min(0.01, remaining))
    finally:
        os.set_blocking(fd, original_blocking)
