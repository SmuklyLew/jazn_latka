from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

_INSTALL_SCHEMA = "latka_polish_reasoning_install/v2"


def project_root_from_package() -> Path:
    """Return the checkout/package root containing ``latka_jazn``."""
    return Path(__file__).resolve().parents[2]


def polish_nlp_data_root(project_root: str | Path | None = None) -> Path:
    """Return the persistent local NLP data directory.

    The default is deliberately inside the Jaźń tree, not ``workspace_runtime``:
    ``<root>/latka_jazn/local_resources/nlp``.  ``LATKA_NLP_DATA_DIR`` remains
    an explicit operator override.
    """
    configured = os.environ.get("LATKA_NLP_DATA_DIR", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    root = Path(project_root).expanduser().resolve() if project_root is not None else project_root_from_package()
    return (root / "latka_jazn" / "local_resources" / "nlp").resolve()


def stanza_model_dir(project_root: str | Path | None = None) -> Path:
    return polish_nlp_data_root(project_root) / "stanza"


def install_manifest_path(project_root: str | Path | None = None) -> Path:
    return polish_nlp_data_root(project_root) / "install_manifest.json"


def read_install_manifest(project_root: str | Path | None = None) -> dict[str, Any] | None:
    path = install_manifest_path(project_root)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None
    if not isinstance(payload, dict) or payload.get("schema_version") != _INSTALL_SCHEMA:
        return None
    return payload


def installed_provider_names(project_root: str | Path | None = None) -> set[str]:
    payload = read_install_manifest(project_root)
    if payload is None:
        return set()
    resources = payload.get("resources")
    if not isinstance(resources, list):
        return set()
    return {
        str(item.get("provider"))
        for item in resources
        if isinstance(item, dict) and item.get("installed") is True and item.get("provider")
    }


def optional_polish_providers_installed(project_root: str | Path | None = None) -> bool:
    return bool(installed_provider_names(project_root))
