"""Negative evidence for Ollama local inference; no implicit cloud authorization."""
from __future__ import annotations

from typing import Any


def ollama_cloud_model_name(name: str) -> bool:
    """Recognize explicit cloud selectors, not a proof that other names are local."""
    leaf = name.strip().casefold().rsplit("/", 1)[-1]
    return leaf.endswith(("-cloud", ":cloud"))


def ollama_remote_model_entry(item: dict[str, Any]) -> bool:
    return bool(
        item.get("remote_model") or item.get("remote_host")
        or ollama_cloud_model_name(str(item.get("name") or ""))
        or ollama_cloud_model_name(str(item.get("model") or ""))
    )


def ollama_model_identity(name: str) -> str:
    """Treat an untagged name as its default latest tag, retaining namespace."""
    name = name.strip().casefold()
    return name if ":" in name.rsplit("/", 1)[-1] else name + ":latest"
