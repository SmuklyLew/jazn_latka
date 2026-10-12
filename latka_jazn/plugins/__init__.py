"""Optional capability plugins for Jaźń."""

from .contracts import PLUGIN_API_VERSION, PLUGIN_ENTRY_POINT_GROUP, PluginDefinition, PluginManifest, PluginStatus
from .registry import discover_plugins, plugin_readiness_report

__all__ = (
    "PLUGIN_API_VERSION",
    "PLUGIN_ENTRY_POINT_GROUP",
    "PluginDefinition",
    "PluginManifest",
    "PluginStatus",
    "discover_plugins",
    "plugin_readiness_report",
)
