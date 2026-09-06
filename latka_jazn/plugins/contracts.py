from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Callable, Mapping

PLUGIN_API_VERSION = "jazn_plugin/v1"
PLUGIN_ENTRY_POINT_GROUP = "jazn.plugins"


@dataclass(frozen=True, slots=True)
class PluginManifest:
    plugin_id: str
    plugin_version: str
    api_contract_version: str
    capabilities: tuple[str, ...]
    classification: str = "optional"
    required_jazn_version: str | None = None
    permissions: tuple[str, ...] = ()
    network_policy: str = "denied_by_default"
    filesystem_policy: str = "capability_scoped"
    lifecycle: str = "operator_enabled_optional"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class PluginDefinition:
    manifest: PluginManifest
    probe: Callable[[], Mapping[str, Any]] | None = None


@dataclass(frozen=True, slots=True)
class PluginStatus:
    plugin_id: str
    source: str
    state: str
    ready: bool | None
    manifest: Mapping[str, Any]
    detail: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "plugin_id": self.plugin_id,
            "source": self.source,
            "state": self.state,
            "ready": self.ready,
            "manifest": dict(self.manifest),
            "detail": dict(self.detail),
        }
