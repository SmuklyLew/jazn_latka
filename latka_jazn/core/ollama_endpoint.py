"""Resolve Ollama client settings without probing services or mutating the environment."""
from __future__ import annotations

import os
from typing import Mapping
from urllib.parse import urlsplit

DEFAULT_OLLAMA_BASE = "http://127.0.0.1:11434"
OLLAMA_BASE_KEYS = ("JAZN_OLLAMA_BASE_URL", "JAZN_LOCAL_LLM_BASE_URL",
                    "JAZN_LOCAL_LLM_API_BASE", "JAZN_LOCAL_MODEL_API_BASE")


def configured_ollama_base(env: Mapping[str, str] | None = None, *, default: str = DEFAULT_OLLAMA_BASE) -> str:
    values = os.environ if env is None else env
    for key in OLLAMA_BASE_KEYS:
        if key in values:
            return values[key].strip().rstrip("/")
    host = values.get("OLLAMA_HOST", "").strip()
    if not host:
        return default
    return host if "://" in host else "http://" + host


def ollama_api_base(value: str | None = None) -> str:
    """Operator probes accept only an explicit, unprivileged IPv4 loopback API."""
    parts = urlsplit(configured_ollama_base() if value is None else value)
    if (parts.scheme != "http" or parts.hostname != "127.0.0.1"
            or parts.port is None or not 1024 <= parts.port <= 65535
            or parts.username is not None or parts.password is not None or parts.path not in {"", "/"}
            or parts.query or parts.fragment):
        raise ValueError("Unsupported local Ollama API base")
    return f"http://127.0.0.1:{parts.port}"


def configured_ollama_port() -> int | None:
    try:
        return urlsplit(ollama_api_base()).port
    except ValueError:
        return None
