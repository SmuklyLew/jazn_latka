from __future__ import annotations

"""RFC 7662 bearer-token verification for the public Jaźń MCP resource server.

The module is intentionally dependency-light. It does not implement an OAuth
Authorization Server and it never mints tokens. It validates bearer tokens by
calling an operator-provided RFC 7662 introspection endpoint and returns the
AccessToken shape expected by the MCP Python SDK.
"""

import asyncio
import base64
from dataclasses import dataclass, field
import json
from typing import Any, Callable, Mapping
from urllib import error, parse, request
from urllib.parse import urlparse

DEFAULT_INTROSPECTION_TIMEOUT_SECONDS = 8.0
DEFAULT_MAX_INTROSPECTION_RESPONSE_BYTES = 64 * 1024

def _require_https_url(value: str, *, field: str) -> str:
    candidate = str(value or "").strip()
    parsed = urlparse(candidate)
    if (
        parsed.scheme.lower() != "https"
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
    ):
        raise ValueError(f"{field}_must_be_absolute_https_url")
    return candidate

def _scope_list(value: object) -> list[str]:
    if isinstance(value, str):
        return [item for item in value.split() if item]
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []

def _audiences(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        item = value.strip()
        return (item,) if item else ()
    if isinstance(value, list):
        return tuple(str(item).strip() for item in value if str(item).strip())
    return ()

@dataclass(frozen=True, slots=True)
class IntrospectionVerifierConfig:
    introspection_url: str
    issuer_url: str
    resource_server_url: str
    client_id: str
    client_secret: str = field(repr=False)
    timeout_seconds: float = DEFAULT_INTROSPECTION_TIMEOUT_SECONDS
    max_response_bytes: int = DEFAULT_MAX_INTROSPECTION_RESPONSE_BYTES

    def __post_init__(self) -> None:
        object.__setattr__(self, "introspection_url", _require_https_url(self.introspection_url, field="introspection_url"))
        object.__setattr__(self, "issuer_url", _require_https_url(self.issuer_url, field="issuer_url"))
        object.__setattr__(self, "resource_server_url", _require_https_url(self.resource_server_url, field="resource_server_url"))
        if not str(self.client_id or "").strip():
            raise ValueError("oauth_introspection_client_id_required")
        if not str(self.client_secret or ""):
            raise ValueError("oauth_introspection_client_secret_required")
        if not (0.5 <= float(self.timeout_seconds) <= 30.0):
            raise ValueError("oauth_introspection_timeout_out_of_range")
        if not (1024 <= int(self.max_response_bytes) <= 1024 * 1024):
            raise ValueError("oauth_introspection_response_limit_out_of_range")

AccessTokenFactory = Callable[..., Any]
HttpOpen = Callable[..., Any]

class Rfc7662TokenVerifier:
    def __init__(self, config: IntrospectionVerifierConfig, *, access_token_factory: AccessTokenFactory | None = None, http_open: HttpOpen | None = None) -> None:
        self.config = config
        self._access_token_factory = access_token_factory
        self._http_open = http_open or request.urlopen

    def _factory(self) -> AccessTokenFactory:
        if self._access_token_factory is not None:
            return self._access_token_factory
        from mcp.server.auth.provider import AccessToken
        return AccessToken

    def _introspect_sync(self, token: str) -> Mapping[str, Any] | None:
        raw_token = str(token or "")
        if not raw_token:
            return None
        body = parse.urlencode({"token": raw_token, "token_type_hint": "access_token"}).encode("utf-8")
        basic = base64.b64encode(f"{self.config.client_id}:{self.config.client_secret}".encode("utf-8")).decode("ascii")
        req = request.Request(
            self.config.introspection_url,
            data=body,
            method="POST",
            headers={
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
                "Authorization": f"Basic {basic}",
                "User-Agent": "jazn-mcp-resource-server/1",
            },
        )
        try:
            with self._http_open(req, timeout=float(self.config.timeout_seconds)) as response:
                status = int(getattr(response, "status", 200))
                if status < 200 or status >= 300:
                    return None
                payload_bytes = response.read(int(self.config.max_response_bytes) + 1)
        except (error.HTTPError, error.URLError, TimeoutError, OSError, ValueError):
            return None
        if len(payload_bytes) > int(self.config.max_response_bytes):
            return None
        try:
            payload = json.loads(payload_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None
        return payload if isinstance(payload, Mapping) else None

    def _validated_access_token(self, token: str, payload: Mapping[str, Any]) -> Any | None:
        if payload.get("active") is not True:
            return None
        client_id = str(payload.get("client_id") or "").strip()
        if not client_id:
            return None
        issuer = str(payload.get("iss") or "").strip()
        if issuer and issuer.rstrip("/") != self.config.issuer_url.rstrip("/"):
            return None
        audience = _audiences(payload.get("aud") or payload.get("resource"))
        expected_resource = self.config.resource_server_url
        if expected_resource not in audience:
            return None
        scopes = _scope_list(payload.get("scope") or payload.get("scopes"))
        expires_at: int | None = None
        if payload.get("exp") is not None:
            try:
                expires_at = int(payload["exp"])
            except (TypeError, ValueError):
                return None
        subject = str(payload.get("sub") or "").strip() or None
        claims: dict[str, Any] = {"iss": issuer} if issuer else {}
        return self._factory()(
            token=token,
            client_id=client_id,
            scopes=scopes,
            expires_at=expires_at,
            resource=expected_resource,
            subject=subject,
            claims=claims or None,
        )

    async def verify_token(self, token: str) -> Any | None:
        payload = await asyncio.to_thread(self._introspect_sync, token)
        if payload is None:
            return None
        return self._validated_access_token(str(token), payload)

__all__ = [
    "DEFAULT_INTROSPECTION_TIMEOUT_SECONDS",
    "DEFAULT_MAX_INTROSPECTION_RESPONSE_BYTES",
    "IntrospectionVerifierConfig",
    "Rfc7662TokenVerifier",
]
