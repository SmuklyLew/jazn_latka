from __future__ import annotations

"""Read-only, offline ChatGPT MCP connection diagnostic.

A correct MCP descriptor is not evidence of a reachable server, a registered
ChatGPT app, or an accepted Jaźń turn. No HTTP request is made and credentials
are never read or printed.
"""

import argparse
import ipaddress
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

MAX_DESCRIPTOR_BYTES = 65536
DESCRIPTOR_FILENAMES = ("mcp.json", ".mcp.json")
RELEVANT_SERVERS = frozenset({"jazn", "ja_runtime"})


def classify_endpoint(endpoint: object) -> str:
    if not isinstance(endpoint, str) or not endpoint.strip():
        return "missing_mcp_endpoint"
    try:
        parsed = urlsplit(endpoint.strip())
        host = parsed.hostname
        _ = parsed.port
    except ValueError:
        return "invalid_mcp_endpoint"
    if (
        not host
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path.rstrip("/") != "/mcp"
    ):
        return "invalid_mcp_endpoint"
    normalized_host = host.rstrip(".").lower()
    if (
        normalized_host in {"localhost", "localhost.localdomain"}
        or normalized_host.endswith((".localhost", ".local"))
    ):
        return "loopback_or_private_endpoint"
    try:
        ip = ipaddress.ip_address(normalized_host)
    except ValueError:
        pass
    else:
        if not ip.is_global:
            return "loopback_or_private_endpoint"
    if parsed.scheme != "https":
        return "insecure_remote_endpoint"
    return "public_https_endpoint_configured_unverified"


def _read_descriptor(path: Path) -> dict[str, Any]:
    if path.stat().st_size > MAX_DESCRIPTOR_BYTES:
        raise ValueError("mcp_descriptor_too_large")
    content = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(content, dict):
        raise ValueError("mcp_descriptor_not_object")
    return content


def inspect_plugin_dir(plugin_dir: Path) -> dict[str, Any]:
    """Inspect local plugin metadata only, without disclosing addresses or tokens."""
    source = Path(plugin_dir)
    found: list[str] = []
    classifications: list[str] = []
    observed_urls: list[str] = []
    for filename in DESCRIPTOR_FILENAMES:
        path = source / filename
        if not path.is_file():
            continue
        found.append(filename)
        try:
            document = _read_descriptor(path)
            servers = document.get("mcpServers")
            if not isinstance(servers, dict):
                raise ValueError("mcp_servers_missing")
            relevant = [
                data for name, data in servers.items()
                if name in RELEVANT_SERVERS
            ]
            if not relevant:
                raise ValueError("jazn_mcp_server_missing")
            for server in relevant:
                if not isinstance(server, dict):
                    raise ValueError("mcp_server_not_object")
                if "url" in server:
                    classifications.append(classify_endpoint(server["url"]))
                    if isinstance(server["url"], str):
                        observed_urls.append(server["url"].strip().rstrip("/"))
                elif "command" in server:
                    classifications.append("local_stdio_only")
                else:
                    classifications.append("missing_mcp_endpoint")
        except (OSError, UnicodeError, ValueError) as exc:
            reason = str(exc) if isinstance(exc, ValueError) else "mcp_descriptor_unreadable"
            classifications.append(reason if reason in {
                "mcp_descriptor_too_large", "mcp_descriptor_not_object",
                "mcp_servers_missing", "jazn_mcp_server_missing",
                "mcp_server_not_object",
            } else "mcp_descriptor_unreadable")

    if not classifications:
        reason = (
            "registered_app_binding_unverified"
            if (source / ".app.json").is_file()
            else "no_jazn_mcp_descriptor"
        )
    elif any(item == "loopback_or_private_endpoint" for item in classifications):
        reason = "loopback_or_private_endpoint"
    elif any(item == "insecure_remote_endpoint" for item in classifications):
        reason = "insecure_remote_endpoint"
    elif all(item == "public_https_endpoint_configured_unverified" for item in classifications):
        reason = (
            "conflicting_mcp_endpoints"
            if len(set(observed_urls)) > 1
            else "public_https_endpoint_configured_unverified"
        )
    else:
        reason = next(
            item for item in classifications
            if item != "public_https_endpoint_configured_unverified"
        )

    return {
        "schema_version": "jazn_chatgpt_mcp_connection_diagnostic/v1",
        "reason_code": reason,
        "descriptor_files_found": found,
        "endpoint_config_valid_for_remote_chatgpt": (
            reason == "public_https_endpoint_configured_unverified"
        ),
        "remote_runtime_verified": False,
        "host_toolset_verified": False,
        "accepted_visible_reply_verified": False,
        "next_action": (
            "deploy_authenticated_streamable_http_over_public_https_or_use_secure_mcp_tunnel"
            if reason in {
                "loopback_or_private_endpoint", "local_stdio_only",
                "insecure_remote_endpoint", "no_jazn_mcp_descriptor",
            }
            else "verify_endpoint_auth_health_then_register_refresh_and_select_chatgpt_app"
            if reason == "public_https_endpoint_configured_unverified"
            else "select_registered_app_and_verify_fresh_current_message_toolset"
            if reason == "registered_app_binding_unverified"
            else "repair_plugin_mcp_descriptor"
        ),
        "truth_boundary": (
            "Offline configuration diagnostics never contact MCP, prove ChatGPT "
            "tool exposure, or authorize a Jaźń visible turn."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only Jaźń ChatGPT MCP connection doctor")
    parser.add_argument("--plugin-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    report = inspect_plugin_dir(args.plugin_dir)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["endpoint_config_valid_for_remote_chatgpt"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
