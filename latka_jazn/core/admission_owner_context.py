"""Verified public principal propagation over the trusted loopback transport.

The daemon capability token authenticates the local gateway/operator.
This context is set by verified ingress, never by MCP tool arguments or
request metadata. The digest is an identity binding, not a bearer credential.
"""
from __future__ import annotations

from contextvars import ContextVar
import hashlib
import json
import re

AUTHENTICATED_HTTP_OWNER: ContextVar[str | None] = ContextVar(
    "jazn_authenticated_http_owner", default=None,
)
ADMISSION_OWNER_HEADER = "X-JAZN-Admission-Owner-Sha256"


def public_owner_digest(subject: str) -> str:
    if not subject or not subject.strip():
        raise ValueError("public_turn_owner_missing")
    return hashlib.sha256(("public_http\0" + subject).encode("utf-8")).hexdigest()


def current_admission_owner() -> str | None:
    subject = AUTHENTICATED_HTTP_OWNER.get()
    return None if subject is None else public_owner_digest(subject)


def is_admission_owner_endpoint(path: str) -> bool:
    return path in {
        "/chat", "/message", "/chat-submit", "/chat-result",
        "/host-finalize", "/chat-finalization",
    } or path.startswith("/chat-result/")

# Reserved for daemon-derived session identities, never a caller authority.
PUBLIC_SESSION_PREFIX = "public-session-v1-"


def is_public_session_id(session_id: str | None) -> bool:
    return bool(session_id and session_id.casefold().startswith(PUBLIC_SESSION_PREFIX))


def admission_session_id(
    session_id: str | None, *, request_id: str, owner_sha256: str | None,
) -> str | None:
    """Derive a stable per-principal session namespace before worker selection.

    A missing client session remains one independent session per request.
    A caller cannot select an already-derived key, even via the local API.
    The original client session remains the input to the admission fingerprint.
    """
    if is_public_session_id(session_id):
        raise ValueError("reserved_public_session_id")
    if owner_sha256 is None:
        return session_id
    if re.fullmatch(r"[0-9a-f]{64}", owner_sha256) is None:
        raise ValueError("invalid_admission_owner")
    material = json.dumps(
        ["public_session/v1", owner_sha256,
         "client_session" if session_id is not None else "request",
         session_id if session_id is not None else request_id],
        ensure_ascii=False, separators=(",", ":"),
    ).encode("utf-8")
    return PUBLIC_SESSION_PREFIX + hashlib.sha256(material).hexdigest()
