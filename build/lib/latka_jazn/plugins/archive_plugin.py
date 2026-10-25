from __future__ import annotations

from typing import Any

from latka_jazn.archive import archive_capability_report
from latka_jazn.version import PACKAGE_VERSION_FULL

from .contracts import PLUGIN_API_VERSION, PluginDefinition, PluginManifest


def _probe_archive() -> dict[str, Any]:
    report = archive_capability_report().to_dict()
    formats = {
        str(item.get("format") or ""): item
        for item in report.get("formats") or []
        if isinstance(item, dict)
    }
    baseline_ready = bool((formats.get("zip") or {}).get("runtime_supported"))
    enhanced = {
        name: bool((formats.get(name) or {}).get("runtime_supported"))
        for name in ("aes_zip", "7z", "rar")
    }
    return {
        "ready": baseline_ready,
        "state": "ready" if all(enhanced.values()) else "degraded" if baseline_ready else "failed",
        "baseline_zip_ready": baseline_ready,
        "enhanced_ready": all(enhanced.values()),
        "enhanced_formats": enhanced,
        "archive_capabilities": report,
        "truth_boundary": (
            "The built-in archive plugin is usable with stdlib ZIP even when optional enhanced backends are absent. "
            "Missing py7zr, pyzipper, rarfile or an external RAR decompressor degrades only the corresponding format."
        ),
    }


plugin = PluginDefinition(
    manifest=PluginManifest(
        plugin_id="archive",
        plugin_version=PACKAGE_VERSION_FULL,
        api_contract_version=PLUGIN_API_VERSION,
        capabilities=("archive.zip", "archive.aes_zip", "archive.7z", "archive.rar"),
        classification="optional",
        required_jazn_version=PACKAGE_VERSION_FULL,
        permissions=("filesystem.read", "filesystem.write.operator_selected"),
        network_policy="denied",
        filesystem_policy="archive_safety_policy_and_operator_selected_paths",
        lifecycle="built_in_optional_capability",
    ),
    probe=_probe_archive,
)
