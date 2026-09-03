from __future__ import annotations

import re
from typing import Any

# v16.3.25.5.2 exports system packages from canonical integrity bytes and exact protected inventory.
DISTRIBUTION_VERSION = "16.3.25.5.2"
PACKAGE_VERSION = "16.3.25.5.2"
PACKAGE_RELEASE_NAME = "package-distribution-convergence"
PACKAGE_VERSION_FULL = (
    f"{PACKAGE_VERSION}-{PACKAGE_RELEASE_NAME}" if PACKAGE_RELEASE_NAME else PACKAGE_VERSION
)
RUNTIME_CONTRACT_VERSION = PACKAGE_VERSION
RUNTIME_CONTRACT_VERSION_FULL = PACKAGE_VERSION_FULL

# These are true serialized format/contract versions. They change only when the
# corresponding contract changes, never merely because PACKAGE_VERSION changes.
_SCHEMA_MAJOR_BY_COMPONENT: dict[str, int] = {
    "source_provenance": 2,
    "package_integrity_manifest": 2,
    "voice_source_contract": 2,
    "self_owned_startup_contract": 2,
    "self_check": 2,
}
# These documents existed before an explicit schema_version field was required.
# Missing schema identity is accepted only as a bounded migration path for these
# known contracts; it is never treated as a current schema.
_LEGACY_UNVERSIONED_SCHEMA_COMPONENTS = frozenset({
    "source_provenance",
    "package_integrity_manifest",
})
_LEGACY_RUNTIME_SCHEMA_SUFFIX_RE = re.compile(
    r"^v?\d+(?:\.\d+)+(?:-[0-9A-Za-z][0-9A-Za-z.-]*)?$"
)


def _component_name(component: str) -> str:
    value = str(component or "").strip().strip("/")
    if not value or "/" in value:
        raise ValueError(f"invalid schema/runtime component name: {component!r}")
    return value


def contract_schema_version(component: str, *, major: int | None = None) -> str:
    """Return a stable serialized-contract identifier.

    Contract schema versions are intentionally independent from PACKAGE_VERSION.
    The default major is v1 unless a component has an explicit current version.
    New true schema/contract consumers should call this function directly.
    """

    name = _component_name(component)
    resolved_major = _SCHEMA_MAJOR_BY_COMPONENT.get(name, 1) if major is None else int(major)
    if resolved_major < 1:
        raise ValueError("contract schema major must be >= 1")
    return f"{name}/v{resolved_major}"


def runtime_version_marker(component: str, *, version: str = PACKAGE_VERSION) -> str:
    """Return an identifier deliberately coupled to the runtime package version."""

    name = _component_name(component)
    value = str(version or PACKAGE_VERSION).strip()
    if not value:
        raise ValueError("runtime version marker requires a non-empty version")
    return f"{name}/{value}"


def release_version_marker(component: str, *, version: str = PACKAGE_VERSION_FULL) -> str:
    """Return an identifier deliberately coupled to the full release identity."""

    name = _component_name(component)
    value = str(version or PACKAGE_VERSION_FULL).strip()
    if not value:
        raise ValueError("release version marker requires a non-empty version")
    return f"{name}/{value}"


def schema_version(component: str, *, version: str | None = None) -> str:
    """Compatibility API for schema callers.

    New/default calls return stable contract schema identifiers. Passing an
    explicit ``version`` preserves the historical runtime-coupled behavior for
    callers that truly need a runtime marker; new code should call
    ``runtime_version_marker`` directly for that purpose.
    """

    if version is not None:
        return runtime_version_marker(component, version=version)
    return contract_schema_version(component)


def schema_contract_metadata(component: str) -> dict[str, Any]:
    """Describe the current schema and supported explicit migration paths."""

    name = _component_name(component)
    current = contract_schema_version(name)
    accepts_unversioned = name in _LEGACY_UNVERSIONED_SCHEMA_COMPONENTS
    return {
        "component": name,
        "current_schema_version": current,
        "accepted_schema_versions": [current],
        "compatibility_policy": "explicit_current_plus_bounded_legacy_migrations",
        "legacy_runtime_coupled_schema": {
            "accepted": True,
            "pattern": f"{name}/<runtime-version>",
            "migration_target": current,
        },
        "legacy_unversioned_schema": {
            "accepted": accepts_unversioned,
            "pattern": None,
            "migration_target": current if accepts_unversioned else None,
        },
    }


def schema_version_compatibility(component: str, value: str | None) -> dict[str, Any]:
    """Classify a serialized schema identifier without conflating it with release versioning."""

    name = _component_name(component)
    current = contract_schema_version(name)
    candidate = str(value or "").strip()
    if candidate == current:
        return {
            "compatible": True,
            "migration_required": False,
            "kind": "current_contract_schema",
            "current_schema_version": current,
            "observed_schema_version": candidate,
        }

    if not candidate and name in _LEGACY_UNVERSIONED_SCHEMA_COMPONENTS:
        return {
            "compatible": True,
            "migration_required": True,
            "kind": "legacy_unversioned_schema",
            "current_schema_version": current,
            "observed_schema_version": None,
        }

    prefix = f"{name}/"
    suffix = candidate[len(prefix):] if candidate.startswith(prefix) else ""
    if suffix and _LEGACY_RUNTIME_SCHEMA_SUFFIX_RE.fullmatch(suffix):
        return {
            "compatible": True,
            "migration_required": True,
            "kind": "legacy_runtime_coupled_schema",
            "current_schema_version": current,
            "observed_schema_version": candidate,
        }

    return {
        "compatible": False,
        "migration_required": False,
        "kind": "unsupported_schema",
        "current_schema_version": current,
        "observed_schema_version": candidate or None,
    }


def version_number(version: str = PACKAGE_VERSION) -> str:
    value = str(version or PACKAGE_VERSION).strip().split("-", 1)[0].lstrip("v")
    return value or PACKAGE_VERSION.lstrip("v")


def active_line(component: str) -> str:
    return runtime_version_marker(component, version=PACKAGE_VERSION)


def version_slug(version: str = PACKAGE_VERSION) -> str:
    return "v" + version_number(version).replace(".", "_")


def generation_mode(prefix: str, *, version: str = PACKAGE_VERSION) -> str:
    return f"{prefix}_{version_slug(version)}"
