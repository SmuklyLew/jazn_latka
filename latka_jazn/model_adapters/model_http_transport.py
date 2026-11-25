"""HTTP inference egress: reject redirects; local routes are loopback-only."""
from __future__ import annotations

from typing import Any
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener


class _DenyRedirect(HTTPRedirectHandler):
    def redirect_request(self, req: Any, fp: Any, code: int, msg: str,
                         headers: Any, newurl: str) -> None:
        return None


def open_model_request(request: Request, *, timeout: float) -> Any:
    """One HTTP request to the selected endpoint; a redirect is an error."""
    return build_opener(_DenyRedirect()).open(request, timeout=timeout)


def open_local_model_request(request: Request, *, timeout: float) -> Any:
    """Validate the immediate destination, not the downstream server behavior."""
    try:
        parsed = urlsplit(request.full_url)
        port = parsed.port
        valid = (
            parsed.scheme in {"http", "https"}
            and parsed.hostname in {"localhost", "127.0.0.1", "::1"}
            and parsed.username is None and parsed.password is None
            and not parsed.query and not parsed.fragment
            and (port is None or 1 <= port <= 65535)
        )
    except ValueError:
        valid = False
    if not valid:
        raise URLError("local_model_destination_not_authorized")
    return build_opener(ProxyHandler({}), _DenyRedirect()).open(request, timeout=timeout)
