"""Verified public principal propagation over the trusted loopback transport.

The daemon capability token authenticates the local gateway/operator.
This context is set by verified ingress, never by MCP tool arguments or
request metadata. The digest is an identity binding, not a bearer credential.
"""
from __future__ import annotations

from contextvars import ContextVar
import hashlib

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
