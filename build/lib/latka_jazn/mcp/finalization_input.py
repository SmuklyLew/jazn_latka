from __future__ import annotations

"""Deterministic HTTP adapter input for the canonical Jaźń phase-2 finalizer.

This layer never accepts or persists a final reply by itself.  It only
constructs the byte-exact checksum required by the existing server-side
continuation-token, turn-authority and persistence transaction.
"""

import hashlib
import hmac
import re

_SHA256_HEX = re.compile(r"[0-9a-fA-F]{64}\Z")
MAX_HOST_FINAL_TEXT_BYTES = 524_288


def validated_final_text_digest(text: str, claimed_sha256: str | None = None) -> str:
    """Return SHA-256 of UTF-8 bytes; fail closed on malformed or stale claims.

    A caller-supplied digest is optional for ChatGPT HTTP.  When present it is
    an assertion, *never* an authority over bytes or runtime finalization.
    """

    if not isinstance(text, str) or not text:
        raise ValueError("final_text_must_be_nonempty_string")
    byte_length = len(text.encode("utf-8", "strict"))
    if byte_length > MAX_HOST_FINAL_TEXT_BYTES:
        raise ValueError("final_text_utf8_limit_exceeded")
    digest = hashlib.sha256(text.encode("utf-8", "strict")).hexdigest()
    if claimed_sha256 is not None:
        if not isinstance(claimed_sha256, str) or not _SHA256_HEX.fullmatch(claimed_sha256):
            raise ValueError("invalid_final_text_sha256")
        if not hmac.compare_digest(digest, claimed_sha256.lower()):
            raise ValueError("final_text_sha256_mismatch")
    return digest
