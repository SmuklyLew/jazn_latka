from __future__ import annotations

"""Single source of truth for memory/storage safety limits.

These limits are runtime/storage invariants, not ChatGPT upload policy. Sandbox ZIP
transport may split a completed archive further, but it must not create individual
members or SQLite shards larger than the bounded values defined here.
"""

DEFAULT_MAX_SQLITE_FILE_BYTES = 480 * 1024 * 1024
DEFAULT_RAW_SEGMENT_TARGET_BYTES = 256 * 1024 * 1024
DEFAULT_RAW_SEGMENT_MAX_BYTES = DEFAULT_MAX_SQLITE_FILE_BYTES
DEFAULT_SYNC_BATCH_WIRE_BYTES = 2_000_000
DEFAULT_SNAPSHOT_CHUNK_BYTES = 16 * 1024 * 1024
DEFAULT_GATEWAY_JSON_BYTES = 4 * 1024 * 1024
DEFAULT_GATEWAY_OBJECT_BYTES = 32 * 1024 * 1024

__all__ = [
    "DEFAULT_GATEWAY_JSON_BYTES",
    "DEFAULT_GATEWAY_OBJECT_BYTES",
    "DEFAULT_MAX_SQLITE_FILE_BYTES",
    "DEFAULT_RAW_SEGMENT_MAX_BYTES",
    "DEFAULT_RAW_SEGMENT_TARGET_BYTES",
    "DEFAULT_SNAPSHOT_CHUNK_BYTES",
    "DEFAULT_SYNC_BATCH_WIRE_BYTES",
]
