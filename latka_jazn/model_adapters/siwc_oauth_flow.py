"""Separate, opt-in Sign in with ChatGPT OAuth flow for OSS/local Jaźń.

MCP OAuth tokens MUST NOT be shared with this provider. This module prepares
PKCE and validates an OAuth callback and OpenAI-signed ID token, but deliberately
does not publish an HTTP callback listener or persist credentials. An operator
must supply a protected credential vault and account/session lifecycle before
connecting this flow to production model selection.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets
import time
import uuid
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit

AUTHORIZATION_URL = "https://auth.openai.com/api/accounts/authorize"
TOKEN_URL = "https://auth.openai.com/api/accounts/oauth/token"
ISSUER = "https://auth.openai.com"
JWKS_URL = ISSUER + "/.well-known/jwks.json"
RESOURCE = "https://api.openai.com/v1"
REQUIRED_SCOPE = "chatgpt.tokens.use.direct"
REQUESTED_SCOPES = "openid profile email offline_access resource.invoke chatgpt.tokens.use.direct"
_MAX_AGE_SECONDS = 600
_ISSUED_CLIENT = re.compile(r"^oaiapp_[A-Za-z0-9._-]{1,120}$")


def _host_id_valid(value: str) -> bool:
    try:
        prefix, raw = value.split(":", 2)[0:2], value.removeprefix("urn:uuid:")
        return value.startswith("urn:uuid:") and uuid.UUID(raw).version == 4
    except (ValueError, AttributeError):
        return False


@dataclass(repr=False)
class LoginAttempt:
    host_id: str
    client_id: str
    redirect_uri: str
    state: str = field(repr=False)
    nonce: str = field(repr=False)
    verifier: str = field(repr=False)
    authorization_url: str = field(repr=False)
    started_at: float = field(default_factory=time.time)
    consumed: bool = False


@dataclass(repr=False, frozen=True)
class AuthorizationGrant:
    code: str = field(repr=False)
    client_id: str
    redirect_uri: str
    verifier: str = field(repr=False)
    expected_nonce: str = field(repr=False)

    def token_form(self) -> dict[str, str]:
        # This is an untrusted code-exchange request, NOT a signed-in user.
        return {
            "grant_type": "authorization_code", "client_id": self.client_id,
            "code": self.code, "code_verifier": self.verifier,
            "redirect_uri": self.redirect_uri, "resource": RESOURCE,
        }


@dataclass(repr=False, frozen=True)
class VerifiedTokens:
    client_id: str
    subject: str
    scopes: frozenset[str]
    access_token: str = field(repr=False)
    refresh_token: str = field(repr=False)
    id_token: str = field(repr=False)
    expires_at: float = field(repr=False)


def begin_login(*, host_id: str, port: int, client_id: str | None = None,
                agent_name: str = "Jaźń") -> LoginAttempt:
    # The operator must persist host_id once per host. It is NOT an auth proof.
    if not _host_id_valid(host_id):
        raise ValueError("siwc_stable_uuid4_host_id_required")
    if type(port) is not int or not 1024 <= port <= 65535:
        raise ValueError("siwc_valid_loopback_port_required")
    if client_id is not None and not _ISSUED_CLIENT.fullmatch(client_id):
        raise ValueError("siwc_issued_client_id_required")
    if not agent_name.strip() or len(agent_name) > 80:
        raise ValueError("siwc_valid_agent_name_required")
    state, nonce, verifier = (secrets.token_urlsafe(32) for _ in range(3))
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).rstrip(b"=").decode("ascii")
    uri = f"http://127.0.0.1:{port}/auth/callback"
    chosen_client = client_id or "dynamic_agent_client"
    params = {
        "client_id": chosen_client,
        "ext_agent_host_id": host_id,
        "redirect_uri": uri,
        "response_type": "code",
        "scope": REQUESTED_SCOPES,
        "resource": RESOURCE,
        "state": state, "nonce": nonce,
        "code_challenge_method": "S256", "code_challenge": challenge,
    }
    if client_id is None:
        params["agent_name_hint"] = agent_name
    return LoginAttempt(
        host_id=host_id, client_id=chosen_client, redirect_uri=uri,
        state=state, nonce=nonce, verifier=verifier,
        authorization_url=AUTHORIZATION_URL + "?" + urlencode(params),
    )


def consume_callback(attempt: LoginAttempt, callback_url: str,
                     *, now: float | None = None) -> AuthorizationGrant:
    # State is consumed once, including on invalid callbacks, to prevent replay.
    if attempt.consumed:
        raise ValueError("siwc_callback_already_consumed")
    attempt.consumed = True
    moment = time.time() if now is None else now
    if moment < attempt.started_at or moment - attempt.started_at > _MAX_AGE_SECONDS:
        raise ValueError("siwc_callback_expired")
    parsed = urlsplit(callback_url)
    expected = urlsplit(attempt.redirect_uri)
    if ((parsed.scheme, parsed.netloc, parsed.path) !=
            (expected.scheme, expected.netloc, expected.path) or parsed.fragment):
        raise ValueError("siwc_callback_redirect_mismatch")
    values = parse_qs(parsed.query, keep_blank_values=True, strict_parsing=True)
    if any(len(v) != 1 for v in values.values()) or "state" not in values:
        raise ValueError("siwc_callback_invalid_parameters")
    if not hmac.compare_digest(values["state"][0], attempt.state):
        raise ValueError("siwc_callback_state_mismatch")
    if values.get("error"):
        raise ValueError("siwc_authorization_denied")
    code = values.get("code", [""])[0]
    if not code or len(code) > 4096:
        raise ValueError("siwc_authorization_code_missing")
    reported_client = values.get("client_id", [""])[0]
    if attempt.client_id == "dynamic_agent_client":
        if not _ISSUED_CLIENT.fullmatch(reported_client):
            raise ValueError("siwc_new_registration_client_id_missing")
        issued = reported_client
    else:
        if reported_client and reported_client != attempt.client_id:
            raise ValueError("siwc_returning_client_id_mismatch")
        issued = attempt.client_id
    return AuthorizationGrant(code=code, client_id=issued,
                              redirect_uri=attempt.redirect_uri,
                              verifier=attempt.verifier,
                              expected_nonce=attempt.nonce)


def verify_token_response(grant: AuthorizationGrant, token_response: dict[str, Any]) -> VerifiedTokens:
    """Cryptographically verify OpenAI ID token via maintained PyJWT/JWKS.

    No plaintext credential storage or adapter activation occurs here.
    A separate vault/refresh manager must durably protect rotating credentials.
    """
    if not isinstance(token_response, dict):
        raise ValueError("siwc_token_response_invalid")
    scopes = frozenset(str(token_response.get("scope", "")).split())
    if REQUIRED_SCOPE not in scopes:
        raise ValueError("siwc_plan_usage_scope_not_granted")
    if str(token_response.get("token_type", "")).lower() != "bearer":
        raise ValueError("siwc_token_type_invalid")
    access, refresh, identity = (
        token_response.get("access_token"),
        token_response.get("refresh_token"),
        token_response.get("id_token"),
    )
    if not all(isinstance(x, str) and x for x in (access, refresh, identity)):
        raise ValueError("siwc_token_set_incomplete")
    expires = token_response.get("expires_in")
    if type(expires) not in (int, float) or not 0 < expires <= 86400:
        raise ValueError("siwc_token_lifetime_invalid")
    try:
        import jwt  # type: ignore[import-not-found]  # optional, install PyJWT[crypto]
        signing_key = jwt.PyJWKClient(JWKS_URL, lifespan=300).get_signing_key_from_jwt(identity)
        claims = jwt.decode(
            identity, signing_key.key, algorithms=["RS256", "ES256"],
            audience=grant.client_id, issuer=ISSUER,
            options={"require": ["exp", "iat", "sub", "nonce"]}, leeway=5,
        )
    except (ImportError, Exception) as exc:
        # Errors must not reveal the supplied token, claims, transport URL or JWKS.
        raise ValueError("siwc_id_token_verification_failed") from None
    if (not isinstance(claims.get("sub"), str) or not claims["sub"] or
            not isinstance(claims.get("nonce"), str) or
            not hmac.compare_digest(claims["nonce"], grant.expected_nonce)):
        raise ValueError("siwc_identity_nonce_or_subject_mismatch")
    return VerifiedTokens(
        client_id=grant.client_id, subject=claims["sub"], scopes=scopes,
        access_token=access, refresh_token=refresh,
        id_token=identity, expires_at=time.time() + float(expires),
    )


__all__ = [
    "begin_login", "consume_callback", "verify_token_response", "LoginAttempt",
    "AuthorizationGrant", "VerifiedTokens", "AUTHORIZATION_URL", "TOKEN_URL",
    "ISSUER", "JWKS_URL", "RESOURCE", "REQUIRED_SCOPE",
]
