from __future__ import annotations

import re
from typing import Any

# v16.3.25.5.68 keeps stable purpose-based test identities and makes Jaźń Test Studio
# non-blocking with live pytest progress, per-test outcomes, cancellation, and scrollable views.
DISTRIBUTION_VERSION = "16.3.25.5.68"
PACKAGE_VERSION = "16.3.25.5.68"
PACKAGE_RELEASE_NAME = "tests-studio-live-progress"
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
    """Backward-compatible bridge for historical callers.

    - `schema_version(component)` returns the true stable contract identifier.
    - `schema_version(component, version=...)` preserves the legacy runtime-coupled
      marker shape for existing migrations/tests, but new schema consumers should
      use `contract_schema_version()` or `runtime_version_marker()` explicitly.
    """

    if version is None:
        return contract_schema_version(component)
    return runtime_version_marker(component, version=version)


def component_schema_version(component: str) -> str:
    """Compatibility alias for the current stable contract schema identifier."""

    return contract_schema_version(component)


def schema_version_is_current(
    component: str,
    value: str | None,
    *,
    expected_major: int | None = None,
) -> bool:
    """Return True only for the current stable schema of `component`."""

    if not value:
        return False
    return str(value).strip() == contract_schema_version(component, major=expected_major)


def classify_schema_version(
    component: str,
    value: str | None,
    *,
    expected_major: int | None = None,
) -> str:
    """Classify a serialized schema version without conflating it with runtime release identity."""

    name = _component_name(component)
    current = contract_schema_version(name, major=expected_major)
    if value is None or not str(value).strip():
        return "legacy_unversioned" if name in _LEGACY_UNVERSIONED_SCHEMA_COMPONENTS else "missing"
    normalized = str(value).strip()
    if normalized == current:
        return "current"
    if normalized.startswith(f"{name}/v"):
        return "other_contract_schema"
    if normalized.startswith(f"{name}/") and _LEGACY_RUNTIME_SCHEMA_SUFFIX_RE.match(
        normalized[len(name) + 1 :]
    ):
        return "legacy_runtime_coupled"
    return "foreign_or_invalid"


def schema_compatibility(
    component: str,
    value: str | None,
    *,
    expected_major: int | None = None,
) -> dict[str, Any]:
    """Return explicit migration/compatibility semantics for schema-bearing documents."""

    name = _component_name(component)
    current = contract_schema_version(name, major=expected_major)
    classification = classify_schema_version(name, value, expected_major=expected_major)
    migratable = classification in {"legacy_unversioned", "legacy_runtime_coupled"}
    return {
        "component": name,
        "observed": value,
        "current": current,
        "classification": classification,
        "current_schema": classification == "current",
        "migration_required": migratable,
        "accepted_for_migration": migratable,
    }


def is_legacy_runtime_schema_marker(component: str, value: str | None) -> bool:
    """Return True only for the historical `component/<runtime-version>` marker shape."""

    return classify_schema_version(component, value) == "legacy_runtime_coupled"


def source_provenance_schema_version() -> str:
    return contract_schema_version("source_provenance")


def package_integrity_manifest_schema_version() -> str:
    return contract_schema_version("package_integrity_manifest")


__all__ = [
    "DISTRIBUTION_VERSION",
    "PACKAGE_VERSION",
    "PACKAGE_RELEASE_NAME",
    "PACKAGE_VERSION_FULL",
    "RUNTIME_CONTRACT_VERSION",
    "RUNTIME_CONTRACT_VERSION_FULL",
    "classify_schema_version",
    "component_schema_version",
    "contract_schema_version",
    "is_legacy_runtime_schema_marker",
    "package_integrity_manifest_schema_version",
    "release_version_marker",
    "runtime_version_marker",
    "schema_compatibility",
    "schema_version",
    "schema_version_is_current",
    "source_provenance_schema_version",
]
