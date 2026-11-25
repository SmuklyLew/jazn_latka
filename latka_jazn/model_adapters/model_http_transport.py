"""HTTP inference egress: reject redirects; local routes are loopback-only."""
from __future__ import annotations

import json
import re
from http.client import IncompleteRead
from time import monotonic
from typing import Any
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from latka_jazn.core.ollama_inference_policy import (
    ollama_cloud_model_name, ollama_model_identity, ollama_remote_model_entry,
)


class _DenyRedirect(HTTPRedirectHandler):
    def redirect_request(self, req: Any, fp: Any, code: int, msg: str,
                         headers: Any, newurl: str) -> None:
        return None


def open_model_request(request: Request, *, timeout: float) -> Any:
    """One HTTP request to the selected endpoint; a redirect is an error."""
    return build_opener(_DenyRedirect()).open(request, timeout=timeout)


def _validate_local_destination(request: Request) -> None:
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
    

class OllamaModelAuthorizationError(ValueError):
    """The metadata gate did not authorize sending an inference body."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)


class OllamaInferenceRequest(Request):
    """Explicit Ollama inference transport; the metadata request carries no prompt."""

    def __init__(self, url: str, *, data: bytes, headers: dict[str, str],
                 model: str, metadata_url: str) -> None:
        super().__init__(url, data=data, headers=headers, method="POST")
        self.model = model
        self.metadata_url = metadata_url


_MAX_OLLAMA_TAGS_BYTES = 4 * 1024 * 1024


def _authorize_ollama_model(request: OllamaInferenceRequest, *, timeout: float) -> None:
    if ollama_cloud_model_name(request.model):
        raise OllamaModelAuthorizationError("ollama_cloud_model_not_authorized")
    metadata = Request(request.metadata_url, method="GET")
    try:
        _validate_local_destination(metadata)
        original, discovery = urlsplit(request.full_url), urlsplit(metadata.full_url)
        if (original.scheme, original.hostname, original.port) != (
            discovery.scheme, discovery.hostname, discovery.port
        ) or not discovery.path.endswith("/api/tags"):
            raise OllamaModelAuthorizationError("ollama_model_metadata_unverified")
        with build_opener(ProxyHandler({}), _DenyRedirect()).open(metadata, timeout=timeout) as response:
            raw = response.read(_MAX_OLLAMA_TAGS_BYTES + 1)
        if len(raw) > _MAX_OLLAMA_TAGS_BYTES:
            raise OllamaModelAuthorizationError("ollama_model_metadata_unverified")
        data = json.loads(raw.decode("utf-8"))
    except OllamaModelAuthorizationError:
        raise
    except (OSError, ValueError, IncompleteRead):
        raise OllamaModelAuthorizationError("ollama_model_metadata_unavailable") from None
    if not isinstance(data, dict) or not isinstance(data.get("models"), list):
        raise OllamaModelAuthorizationError("ollama_model_metadata_unverified")
    wanted = ollama_model_identity(request.model)
    matches = [
        item for item in data["models"] if isinstance(item, dict)
        and any(isinstance(item.get(field), str)
                and ollama_model_identity(item[field]) == wanted for field in ("name", "model"))
    ]
    if any(ollama_remote_model_entry(item) for item in matches):
        raise OllamaModelAuthorizationError("ollama_cloud_model_not_authorized")
    if not matches:
        raise OllamaModelAuthorizationError("ollama_model_metadata_unverified")
    for item in matches:
        # Both name fields, when supplied, must describe the selected model.
        # Require the installed-model metadata documented by Ollama, not a
        # bare name supplied by an OpenAI-compatible proxy.
        if (any(field in item and (not isinstance(item[field], str)
                                   or ollama_model_identity(item[field]) != wanted)
                for field in ("name", "model"))
                or type(item.get("size")) is not int or item["size"] <= 0
                or not isinstance(item.get("digest"), str)
                or re.fullmatch(r"(?:sha256:)?[0-9a-fA-F]{64}", item["digest"]) is None):
            raise OllamaModelAuthorizationError("ollama_model_metadata_unverified")


def open_local_model_request(request: Request, *, timeout: float) -> Any:
    """Loopback only, no redirects; Ollama POST additionally requires fresh tags."""
    _validate_local_destination(request)
    if isinstance(request, OllamaInferenceRequest):
        started = monotonic()
        _authorize_ollama_model(request, timeout=min(timeout, 8.0))
        timeout -= monotonic() - started
        if timeout <= 0:
            raise OllamaModelAuthorizationError("ollama_model_metadata_unavailable")
    return build_opener(ProxyHandler({}), _DenyRedirect()).open(request, timeout=timeout)
