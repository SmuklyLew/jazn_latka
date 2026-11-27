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
import secrets
from pathlib import Path

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

# The current engine has shared autobiographical MEMORY, retrieval, wake-state
# and global runtime_state. A session namespace is not a tenant data boundary.
# This is an operator-owned, local-only binding, never created by first use.
PRIVATE_CONTEXT_OWNER_FILE = Path(".settings_local/public_private_context_owner.json")
PRIVATE_CONTEXT_OWNER_SCHEMA = "public_private_context_owner/v1"


def public_private_context_authorized(root: Path, owner_sha256: str | None) -> bool:
    """Fail closed for public use of the existing single-owner private context.

    The operator must explicitly attest the existing context belongs to the
    selected verified principal. Never infer ownership from a token, a task
    row, the first caller, memory_mode, or the absence of a private archive.
    A trusted operator must not reassign this file to another tenant on an
    existing installation; a different tenant needs independently scoped data.
    """
    if not isinstance(owner_sha256, str) or re.fullmatch(r"[0-9a-f]{64}", owner_sha256) is None:
        return False
    try:
        base = Path(root).resolve(strict=True)
        binding = base / PRIVATE_CONTEXT_OWNER_FILE
        resolved = binding.resolve(strict=True)
        if resolved != binding or not resolved.is_file():
            return False
        with resolved.open("rb") as stream:
            raw = stream.read(4097)
        if len(raw) > 4096:
            return False
        payload = json.loads(raw)
        if not isinstance(payload, dict) or set(payload) != {
            "schema_version", "owner_sha256", "existing_shared_context_reviewed",
        }:
            return False
        configured = payload.get("owner_sha256")
        return (
            payload.get("schema_version") == PRIVATE_CONTEXT_OWNER_SCHEMA
            and payload.get("existing_shared_context_reviewed") is True
            and isinstance(configured, str)
            and re.fullmatch(r"[0-9a-f]{64}", configured) is not None
            and secrets.compare_digest(configured, owner_sha256)
        )
    except (OSError, ValueError, TypeError, RecursionError):
        return False
