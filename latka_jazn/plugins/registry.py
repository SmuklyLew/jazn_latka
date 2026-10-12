from __future__ import annotations

from importlib import metadata
from typing import Any, Iterable

from .archive_plugin import plugin as archive_plugin
from .contracts import (
    PLUGIN_API_VERSION,
    PLUGIN_ENTRY_POINT_GROUP,
    PluginDefinition,
    PluginStatus,
)

_BUILTINS: tuple[PluginDefinition, ...] = (archive_plugin,)


def _entry_points() -> Iterable[metadata.EntryPoint]:
    discovered = metadata.entry_points()
    if hasattr(discovered, "select"):
        return discovered.select(group=PLUGIN_ENTRY_POINT_GROUP)
    return discovered.get(PLUGIN_ENTRY_POINT_GROUP, ())  # type: ignore[union-attr]


def _status_from_definition(definition: PluginDefinition, *, source: str) -> PluginStatus:
    manifest = definition.manifest
    if manifest.api_contract_version != PLUGIN_API_VERSION:
        return PluginStatus(
            plugin_id=manifest.plugin_id,
            source=source,
            state="quarantined",
            ready=False,
            manifest=manifest.to_dict(),
            detail={"reason": "plugin_api_contract_mismatch", "expected": PLUGIN_API_VERSION},
        )
    if definition.probe is None:
        return PluginStatus(
            plugin_id=manifest.plugin_id,
            source=source,
            state="discovered",
            ready=None,
            manifest=manifest.to_dict(),
            detail={"probe": "not_provided"},
        )
    try:
        detail = dict(definition.probe())
    except Exception as exc:  # Optional plugin failures must never escape into core startup/doctor.
        return PluginStatus(
            plugin_id=manifest.plugin_id,
            source=source,
            state="failed",
            ready=False,
            manifest=manifest.to_dict(),
            detail={"error_type": type(exc).__name__, "error": str(exc)},
        )
    state = str(detail.get("state") or ("ready" if detail.get("ready") is True else "degraded"))
    ready_raw = detail.get("ready")
    ready = ready_raw if isinstance(ready_raw, bool) else None
    return PluginStatus(
        plugin_id=manifest.plugin_id,
        source=source,
        state=state,
        ready=ready,
        manifest=manifest.to_dict(),
        detail=detail,
    )


def discover_plugins(*, load_external: bool = False) -> dict[str, Any]:
    statuses = [_status_from_definition(item, source="builtin") for item in _BUILTINS]
    builtin_ids = {item.plugin_id for item in statuses}
    external: list[PluginStatus] = []
    try:
        points = sorted(_entry_points(), key=lambda item: (item.name, item.value))
    except Exception as exc:
        points = []
        external.append(
            PluginStatus(
                plugin_id="<entry-point-discovery>",
                source="entry_point",
                state="failed",
                ready=False,
                manifest={},
                detail={"error_type": type(exc).__name__, "error": str(exc)},
            )
        )
    for point in points:
        if point.name in builtin_ids and point.value == "latka_jazn.plugins.archive_plugin:plugin":
            continue
        if not load_external:
            external.append(
                PluginStatus(
                    plugin_id=point.name,
                    source="entry_point",
                    state="discovered",
                    ready=None,
                    manifest={"entry_point_group": PLUGIN_ENTRY_POINT_GROUP, "entry_point": point.value},
                    detail={"loaded": False, "truth_boundary": "Discovery does not import third-party plugin code."},
                )
            )
            continue
        try:
            loaded = point.load()
            if not isinstance(loaded, PluginDefinition):
                raise TypeError("entry point did not expose PluginDefinition")
            external.append(_status_from_definition(loaded, source="entry_point"))
        except Exception as exc:
            external.append(
                PluginStatus(
                    plugin_id=point.name,
                    source="entry_point",
                    state="quarantined",
                    ready=False,
                    manifest={"entry_point_group": PLUGIN_ENTRY_POINT_GROUP, "entry_point": point.value},
                    detail={"error_type": type(exc).__name__, "error": str(exc)},
                )
            )
    combined = statuses + external
    return {
        "schema_version": "jazn_plugin_registry/v1",
        "api_contract_version": PLUGIN_API_VERSION,
        "entry_point_group": PLUGIN_ENTRY_POINT_GROUP,
        "ok": True,
        "plugin_count": len(combined),
        "plugins": [item.to_dict() for item in combined],
        "load_external": bool(load_external),
        "truth_boundary": (
            "Built-in optional plugins are probed fail-closed per plugin. Third-party entry points are discovered "
            "without importing them unless an explicit operator path requests loading. Plugin failure is not core failure."
        ),
    }


def plugin_readiness_report() -> dict[str, Any]:
    report = discover_plugins(load_external=False)
    rows = report["plugins"]
    archive = next((item for item in rows if item.get("plugin_id") == "archive"), None)
    return {
        **report,
        "archive_plugin_ready": None if archive is None else archive.get("ready"),
        "archive_plugin_state": None if archive is None else archive.get("state"),
        "optional_failures": [
            item.get("plugin_id")
            for item in rows
            if item.get("state") in {"failed", "quarantined"}
        ],
        "blocks_runtime_core": False,
    }
