from __future__ import annotations

"""Portable Agent Plugin packaging for a deployed Jaźń MCP endpoint.

The portable Agent Plugins package remains the canonical distributable form.
For local/workspace ChatGPT testing, an optional registered app id can also be
bound through .app.json after the MCP server has been connected in Developer
Mode. Packaging never claims that the ChatGPT host has installed the app.
"""

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
PLUGIN_DOCUMENT_NAMES = ("plugin.json", "mcp.json", ".app.json")
REPOSITORY_URL = "https://github.com/SmuklyLew/jazn_latka"
_REGISTERED_APP_PREFIXES = (
    "plugin_asdk_app_",
    "asdk_app_",
    "connector_",
    "templated_apps_",
)


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
    if any(
        ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
        for ch in candidate
    ):
        raise ValueError("chatgpt_registered_app_id_invalid")
    return candidate


def _openai_extension(*, registered_app_id: str | None) -> dict[str, Any]:
    extension: dict[str, Any] = {
        "interface": {
            "displayName": "Jaźń Runtime",
            "shortDescription": "Persistent Jaźń runtime for validated conversation turns.",
            "longDescription": (
                "Routes the current ChatGPT message through a persistent Jaźń runtime when "
                "the Jaźń app is exposed, with idempotent resume/finalization and fail-closed "
                "display_exact semantics."
            ),
            "developerName": "Jaźń",
            "category": "Productivity",
            "capabilities": ["Read", "Write"],
            "websiteURL": REPOSITORY_URL,
            "defaultPrompt": [
                "Verify Jaźń runtime readiness and required turn tools for this message; require the complete current-message toolset.",
                "Route this message through Jaźń using the validated turn/finalization contract.",
                "If the required Jaźń tools are missing or stale, fail closed and refresh/recreate the app; never fall back to a local ChatGPT executor.",
            ],
            "brandColor": "#5B4B8A",
        }
    }
    if registered_app_id is not None:
        extension["apps"] = "./.app.json"
    return extension


def build_portable_plugin_documents(
    endpoint: str | None = None,
    *,
    package_version: str = PACKAGE_VERSION_FULL,
    registered_app_id: str | None = None,
) -> dict[str, dict[str, Any]]:
    endpoint_value = str(endpoint or "").strip()
    remote_endpoint = (
        validate_remote_mcp_endpoint(endpoint_value)
        if endpoint_value
        else None
    )
    app_id = (
        validate_registered_app_id(registered_app_id)
        if registered_app_id is not None
        else None
    )
    if remote_endpoint is None and app_id is None:
        raise ValueError("chatgpt_plugin_requires_endpoint_or_registered_app_id")
    plugin: dict[str, Any] = {
        "$schema": PLUGIN_SCHEMA,
        "name": PLUGIN_NAME,
        "version": str(package_version),
        "description": (
            (
                "Authenticated ChatGPT and agent access to one persistent Jaźń runtime "
                "through Streamable HTTP MCP."
            )
            if remote_endpoint is not None
            else (
                "ChatGPT binding to an already registered Jaźń MCP app backed by one "
                "persistent runtime."
            )
        ),
        "author": {"name": "SmuklyLew"},
        "repository": REPOSITORY_URL,
        "keywords": ["jazn", "mcp", "chatgpt", "persistent-runtime"],
        "extensions": {
            "com.openai": _openai_extension(registered_app_id=app_id),
        },
    }
    documents: dict[str, dict[str, Any]] = {
        "plugin.json": plugin,
    }
    if remote_endpoint is not None:
        documents["mcp.json"] = {
            "$schema": MCP_SCHEMA,
            "mcpServers": {
                MCP_SERVER_NAME: {
                    "type": "streamable-http",
                    "url": remote_endpoint,
                }
            },
        }
    if app_id is not None:
        documents[".app.json"] = {
            "apps": {
                MCP_SERVER_NAME: {
                    "id": app_id,
                    "required": True,
                }
            }
        }
    return documents


def _json_bytes(value: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_bytes(payload)
    tmp.replace(path)


@dataclass(frozen=True, slots=True)
class PluginPackageResult:
    output_dir: str
    endpoint: str | None
    package_version: str
    registered_app_id: str | None
    files: tuple[dict[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": True,
            "output_dir": self.output_dir,
            "endpoint": self.endpoint,
            "package_version": self.package_version,
            "registered_app_id": self.registered_app_id,
            "files": [dict(item) for item in self.files],
            "truth_boundary": (
                "Generating a plugin package proves only that package metadata is ready. "
                "It does not deploy or register an MCP endpoint/app, configure OAuth, "
                "install/publish the plugin, or prove that the current ChatGPT host exposes "
                "callable Jaźń actions."
            ),
        }


def write_portable_plugin_package(
    output_dir: Path,
    endpoint: str | None = None,
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
    existing = [
        target / name
        for name in PLUGIN_DOCUMENT_NAMES
        if (target / name).exists()
    ]
    if existing and not force:
        raise FileExistsError("chatgpt_plugin_package_target_exists_use_force")

    file_records: list[dict[str, Any]] = []
    for name, value in documents.items():
        payload = _json_bytes(value)
        destination = target / name
        _atomic_write(destination, payload)
        file_records.append(
            {
                "path": str(destination),
                "sha256": hashlib.sha256(payload).hexdigest(),
                "size_bytes": len(payload),
            }
        )

    if force:
        for stale_name in PLUGIN_DOCUMENT_NAMES:
            if stale_name in documents:
                continue
            stale_path = target / stale_name
            if stale_path.is_file():
                stale_path.unlink()

    normalized_app_id = (
        validate_registered_app_id(registered_app_id)
        if registered_app_id is not None
        else None
    )
    endpoint_value = str(endpoint or "").strip()
    normalized_endpoint = (
        validate_remote_mcp_endpoint(endpoint_value)
        if endpoint_value
        else None
    )
    return PluginPackageResult(
        output_dir=str(target),
        endpoint=normalized_endpoint,
        package_version=str(package_version),
        registered_app_id=normalized_app_id,
        files=tuple(file_records),
    )


__all__ = [
    "MCP_SCHEMA",
    "MCP_SERVER_NAME",
    "PLUGIN_NAME",
    "PLUGIN_SCHEMA",
    "PluginPackageResult",
    "build_portable_plugin_documents",
    "validate_registered_app_id",
    "validate_remote_mcp_endpoint",
    "write_portable_plugin_package",
]
