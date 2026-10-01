from __future__ import annotations

"""Portable Agent Plugin packaging for a deployed public Jaźń MCP endpoint."""

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlparse

from latka_jazn.version import PACKAGE_VERSION_FULL

PLUGIN_SCHEMA = "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
MCP_SCHEMA = "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json"
PLUGIN_NAME = "jazn-runtime"
MCP_SERVER_NAME = "jazn"
REPOSITORY_URL = "https://github.com/SmuklyLew/jazn_latka"

def validate_remote_mcp_endpoint(value: str) -> str:
    candidate = str(value or "").strip()
    parsed = urlparse(candidate)
    if (
        parsed.scheme.lower() != "https"
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("chatgpt_plugin_endpoint_must_be_absolute_https_url")
    normalized_path = parsed.path.rstrip("/") or "/"
    if normalized_path != "/mcp":
        raise ValueError("chatgpt_plugin_endpoint_path_must_be_/mcp")
    return candidate.rstrip("/")

def validate_registered_app_id(value: str) -> str:
    candidate = str(value or "").strip()
    if not candidate or not candidate.startswith(_REGISTERED_APP_PREFIXES):
        raise ValueError("chatgpt_registered_app_id_invalid")
    if any(ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for ch in candidate):
        raise ValueError("chatgpt_registered_app_id_invalid")
    return candidate


def build_portable_plugin_documents(
    endpoint: str,
    *,
    package_version: str = PACKAGE_VERSION_FULL,
    registered_app_id: str | None = None,
) -> dict[str, dict[str, Any]]:
    remote_endpoint = validate_remote_mcp_endpoint(endpoint)
    plugin = {
        "$schema": PLUGIN_SCHEMA,
        "name": PLUGIN_NAME,
        "version": str(package_version),
        "description": (
            "Authenticated ChatGPT/agent access to one persistent Jaźń runtime "
            "through its public Streamable HTTP MCP ingress."
        ),
        "author": {"name": "SmuklyLew"},
        "repository": REPOSITORY_URL,
        "keywords": ["jazn", "mcp", "chatgpt", "persistent-runtime"],
    }
    mcp = {
        "$schema": MCP_SCHEMA,
        "mcpServers": {
            MCP_SERVER_NAME: {
                "type": "streamable-http",
                "url": remote_endpoint,
            }
        },
    }
    return {"plugin.json": plugin, "mcp.json": mcp}

def _json_bytes(value: Mapping[str, Any]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")

def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_bytes(payload)
    tmp.replace(path)

@dataclass(frozen=True, slots=True)
class PluginPackageResult:
    output_dir: str
    endpoint: str
    package_version: str
    files: tuple[dict[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": True,
            "output_dir": self.output_dir,
            "endpoint": self.endpoint,
            "package_version": self.package_version,
            "files": [dict(item) for item in self.files],
            "truth_boundary": (
                "Generating a portable plugin package proves only that the package metadata is ready. "
                "It does not deploy the HTTPS MCP endpoint, configure OAuth, install or publish the plugin "
                "in ChatGPT, or prove that the current ChatGPT host exposes the app capability."
            ),
        }

def write_portable_plugin_package(
    output_dir: Path,
    endpoint: str,
    *,
    package_version: str = PACKAGE_VERSION_FULL,
    registered_app_id: str | None = None,
    force: bool = False,
) -> PluginPackageResult:
    target = Path(output_dir).expanduser().resolve()
    target.mkdir(parents=True, exist_ok=True)
    documents = build_portable_plugin_documents(
        endpoint,
        package_version=package_version,
        registered_app_id=registered_app_id,
    )
    existing = [target / name for name in documents if (target / name).exists()]
    if existing and not force:
        raise FileExistsError("chatgpt_plugin_package_target_exists_use_force")
    file_records: list[dict[str, Any]] = []
    for name, value in documents.items():
        payload = _json_bytes(value)
        destination = target / name
        _atomic_write(destination, payload)
        file_records.append({
            "path": str(destination),
            "sha256": hashlib.sha256(payload).hexdigest(),
            "size_bytes": len(payload),
        })
    return PluginPackageResult(
        output_dir=str(target),
        endpoint=validate_remote_mcp_endpoint(endpoint),
        package_version=str(package_version),
        files=tuple(file_records),
    )

__all__ = [
    "MCP_SCHEMA",
    "MCP_SERVER_NAME",
    "PLUGIN_NAME",
    "PLUGIN_SCHEMA",
    "PluginPackageResult",
    "build_portable_plugin_documents",
    "validate_remote_mcp_endpoint",
    "write_portable_plugin_package",
]
